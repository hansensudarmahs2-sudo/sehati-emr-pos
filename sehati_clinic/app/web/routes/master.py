"""
Master Data web routes (Owner + Superadmin only):

Master Treatment:
- GET  /web/master/treatment                            list + filter
- GET  /web/master/treatment/tambah                     form tambah
- POST /web/master/treatment/tambah                     submit tambah
- GET  /web/master/treatment/{id}                       form edit
- POST /web/master/treatment/{id}                       submit edit
- POST /web/master/treatment/{id}/toggle-active         aktifkan/nonaktifkan

Master Produk:
- GET  /web/master/produk                               list + filter
- GET  /web/master/produk/tambah                        form tambah
- POST /web/master/produk/tambah                        submit tambah
- GET  /web/master/produk/{id}                          form edit
- POST /web/master/produk/{id}                          submit edit (profile only)
- POST /web/master/produk/{id}/toggle-active            aktifkan/nonaktifkan
- (POST /web/master/produk/{id}/restock REMOVED — pakai Pengadaan/PO instead, DEC-040)

Role gate: Owner + Superadmin (MASTER_DATA_ROLES).
"""

from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.schemas.master_membership import (
    MasterMembershipCreate,
    MasterMembershipUpdate,
)
from app.schemas.master_produk import (
    MasterProdukCreate,
    MasterProdukUpdate,
    RestockProdukRequest,
)
from app.services.inventory_service import InventoryService
from app.services.master_produk_service import MasterProdukService
from app.services.master_treatment_service import MasterTreatmentService
from app.services.master_membership_service import MasterMembershipService
from app.services.membership_benefit_service import MembershipBenefitService
from app.schemas.membership_benefit import BenefitTreatmentCreate, BenefitTreatmentUpdate
from app.web.routes._shared import (
    build_shell_context,
    get_user_from_cookie,
    require_master_data_role,
    require_purchasing_full_role,
    templates,
)

from app.db.models import InventoryStok, KategoriKomponenTreatmentEnum, TreatmentKomponen
from app.repositories.inventory_repo import InventoryRepository
from app.services.audit_service import AuditService


router = APIRouter(tags=["Web Master Data"])


_VALID_ROLE_PELAKSANA = ["Dokter", "Perawat", "FO", "Apoteker", "Kasir", "Admin", "Owner"]
_VALID_TIPE_PRODUK = ["RETAIL", "CABIN", "ALAT"]


def _403():
    return HTMLResponse("<div style='padding:2rem'>403 - Hanya Owner/Superadmin.</div>", status_code=403)


# =============================================================================
# MASTER TREATMENT
# =============================================================================
@router.get("/master/treatment", response_class=HTMLResponse)
def master_treatment_list(request: Request, db: DbSession, q: str = "", only_active: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    only_active_bool = only_active == "1"
    try:
        treatments = MasterTreatmentService(db).list_all(
            keyword=q or None, only_active=only_active_bool, limit=500,
        )
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    data = [
        {
            "id_treatment": t.id_treatment,
            "nama_treatment": t.nama_treatment,
            "role_pelaksana": t.role_pelaksana,
            "durasi_menit": t.durasi_menit,
            "harga": float(t.harga),
            "is_active": bool(t.is_active),
            "butuh_otorisasi": bool(t.butuh_otorisasi),
        }
        for t in treatments
    ]

    ctx = build_shell_context(
        user, db=db, current_path="/web/master/treatment",
        page_subtitle="Master Treatment",
        data=data, total=len(data),
        q=q, only_active=only_active_bool,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_treatment_list.html", ctx)


@router.get("/master/treatment/tambah", response_class=HTMLResponse)
def master_treatment_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    ctx = build_shell_context(
        user, db=db, current_path="/web/master/treatment",
        page_subtitle="Tambah Treatment Baru",
        form={}, roles=_VALID_ROLE_PELAKSANA, error=None,
        is_edit=False,
    )
    return templates.TemplateResponse(request, "master_treatment_form.html", ctx)


@router.post("/master/treatment/tambah", response_class=HTMLResponse)
def master_treatment_tambah_submit(
    request: Request,
    db: DbSession,
    nama_treatment: str = Form(...),
    role_pelaksana: str = Form(...),
    durasi_menit: int = Form(..., gt=0),
    harga: float = Form(..., ge=0),
    harga_paket: float = Form(default=0, ge=0),
    butuh_otorisasi: str = Form(default=""),
    default_rentang_mulai_minggu: int = Form(default=0, ge=0),
    default_rentang_akhir_minggu: int = Form(default=12, ge=0),
    # DEC-060 Komisi Hybrid
    bhp_per_pakai_nominal: float = Form(default=0, ge=0),
    komisi_dokter_tipe: str = Form(default=""),
    komisi_dokter_value: float = Form(default=0, ge=0),
    komisi_perawat_tipe: str = Form(default=""),
    komisi_perawat_value: float = Form(default=0, ge=0),
    pajak_persen: float = Form(default=0, ge=0),
    pajak_nominal: float = Form(default=0, ge=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        created = MasterTreatmentService(db).create_treatment(
            nama_treatment=nama_treatment,
            role_pelaksana=role_pelaksana,
            durasi_menit=durasi_menit,
            harga=harga,
            harga_paket=(harga_paket if harga_paket > 0 else None),
            butuh_otorisasi=(butuh_otorisasi == "1"),
            default_rentang_mulai_minggu=default_rentang_mulai_minggu,
            default_rentang_akhir_minggu=default_rentang_akhir_minggu,
            bhp_per_pakai_nominal=bhp_per_pakai_nominal,
            komisi_dokter_tipe=(komisi_dokter_tipe or None),
            komisi_dokter_value=komisi_dokter_value,
            komisi_perawat_tipe=(komisi_perawat_tipe or None),
            komisi_perawat_value=komisi_perawat_value,
            pajak_persen=pajak_persen,
            pajak_nominal=(pajak_nominal if pajak_nominal > 0 else None),
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/treatment?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/treatment?ok={quote(f'Treatment {created.nama_treatment} berhasil dibuat.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/master/treatment/{id_treatment}", response_class=HTMLResponse)
def master_treatment_edit_form(id_treatment: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        t = MasterTreatmentService(db).get_by_id(id_treatment)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)

    form = {
        "id_treatment": t.id_treatment,
        "nama_treatment": t.nama_treatment,
        "role_pelaksana": t.role_pelaksana,
        "durasi_menit": t.durasi_menit,
        "harga": float(t.harga),
        "harga_paket": float(t.harga_paket) if t.harga_paket else 0,
        "butuh_otorisasi": bool(t.butuh_otorisasi),
        "is_active": bool(t.is_active),
        "default_rentang_mulai_minggu": t.default_rentang_mulai_minggu,
        "default_rentang_akhir_minggu": t.default_rentang_akhir_minggu,
        # DEC-060 Komisi Hybrid
        "bhp_per_pakai_nominal": float(t.bhp_per_pakai_nominal or 0),
        "komisi_dokter_tipe": t.komisi_dokter_tipe or "",
        "komisi_dokter_value": float(t.komisi_dokter_value or 0),
        "komisi_perawat_tipe": t.komisi_perawat_tipe or "",
        "komisi_perawat_value": float(t.komisi_perawat_value or 0),
        "pajak_persen": float(t.pajak_persen or 0),
        "pajak_nominal": float(t.pajak_nominal or 0),
    }

    # Fetch komponen treatment (bahan + alat) + master bahan untuk dropdown
    from sqlalchemy import select as _sel
    komponen_rows = db.execute(
        _sel(TreatmentKomponen, InventoryStok)
        .outerjoin(InventoryStok, TreatmentKomponen.id_bahan == InventoryStok.id_bahan)
        .where(TreatmentKomponen.id_treatment == id_treatment)
        .order_by(TreatmentKomponen.id_komponen.asc())
    ).all()
    komponen_list = [
        {
            "id_komponen": k.id_komponen,
            "kategori": k.kategori.value if hasattr(k.kategori, "value") else str(k.kategori),
            "id_bahan": k.id_bahan,
            "nama_bahan": b.nama_bahan if b else f"(bahan #{k.id_bahan})",
            "qty": float(k.qty),
            "satuan": k.satuan,
        }
        for k, b in komponen_rows
    ]
    bahan_list = InventoryRepository(db).list_all(limit=500)
    master_bahan = [
        {"id_bahan": b.id_bahan, "nama_bahan": b.nama_bahan, "satuan": b.satuan or ""}
        for b in bahan_list
    ]

    ctx = build_shell_context(
        user, db=db, current_path="/web/master/treatment",
        page_subtitle=f"Edit Treatment - {t.nama_treatment}",
        form=form, roles=_VALID_ROLE_PELAKSANA,
        komponen_list=komponen_list,
        master_bahan=master_bahan,
        error=request.query_params.get("err"),
        flash=request.query_params.get("ok"),
        is_edit=True,
    )
    return templates.TemplateResponse(request, "master_treatment_form.html", ctx)


@router.post("/master/treatment/{id_treatment}", response_class=HTMLResponse)
def master_treatment_edit_submit(
    id_treatment: int,
    request: Request,
    db: DbSession,
    nama_treatment: str = Form(...),
    role_pelaksana: str = Form(...),
    durasi_menit: int = Form(..., gt=0),
    harga: float = Form(..., ge=0),
    harga_paket: float = Form(default=0, ge=0),
    butuh_otorisasi: str = Form(default=""),
    default_rentang_mulai_minggu: int = Form(default=0, ge=0),
    default_rentang_akhir_minggu: int = Form(default=12, ge=0),
    # DEC-060 Komisi Hybrid
    bhp_per_pakai_nominal: float = Form(default=0, ge=0),
    komisi_dokter_tipe: str = Form(default=""),
    komisi_dokter_value: float = Form(default=0, ge=0),
    komisi_perawat_tipe: str = Form(default=""),
    komisi_perawat_value: float = Form(default=0, ge=0),
    pajak_persen: float = Form(default=0, ge=0),
    pajak_nominal: float = Form(default=0, ge=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    data = {
        "nama_treatment": nama_treatment.strip(),
        "role_pelaksana": role_pelaksana,
        "durasi_menit": durasi_menit,
        "harga": harga,
        "harga_paket": (harga_paket if harga_paket > 0 else None),
        "butuh_otorisasi": butuh_otorisasi == "1",
        "default_rentang_mulai_minggu": default_rentang_mulai_minggu,
        "default_rentang_akhir_minggu": default_rentang_akhir_minggu,
        # DEC-060 Komisi Hybrid (service akan validasi tipe + clamp value)
        "bhp_per_pakai_nominal": bhp_per_pakai_nominal,
        "komisi_dokter_tipe": (komisi_dokter_tipe or None),
        "komisi_dokter_value": komisi_dokter_value,
        "komisi_perawat_tipe": (komisi_perawat_tipe or None),
        "komisi_perawat_value": komisi_perawat_value,
        "pajak_persen": pajak_persen,
        "pajak_nominal": (pajak_nominal if pajak_nominal > 0 else None),
    }
    try:
        MasterTreatmentService(db).update_treatment(
            id_treatment=id_treatment, data=data,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/treatment/{id_treatment}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/treatment?ok={quote('Treatment berhasil diupdate.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/treatment/{id_treatment}/toggle-active")
def master_treatment_toggle_active(
    id_treatment: int, request: Request, db: DbSession,
    is_active: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    new_state = is_active == "1"
    try:
        MasterTreatmentService(db).set_active(
            id_treatment=id_treatment, is_active=new_state,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/treatment?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    label = "diaktifkan" if new_state else "dinonaktifkan"
    return RedirectResponse(
        url=f"/web/master/treatment?ok={quote(f'Treatment berhasil {label}.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# MASTER PRODUK
# =============================================================================
@router.get("/master/produk", response_class=HTMLResponse)
def master_produk_list(request: Request, db: DbSession, q: str = "", tipe: str = "", only_active: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    only_active_bool = only_active == "1"
    tipe_filter = tipe.upper() if tipe else None
    try:
        produk_list = MasterProdukService(db).list_all(
            keyword=q or None, tipe=tipe_filter,
            only_active=only_active_bool, limit=500,
        )
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    data = [
        {
            "id_produk": p.id_produk,
            "kode_produk": p.kode_produk,
            "nama_produk": p.nama_produk,
            "kandungan": p.kandungan,
            "nama_dagang": p.nama_dagang,
            "tipe_produk": p.tipe_produk,
            "satuan": p.satuan,
            "harga_jual": float(p.harga_jual),
            "stok_terkini": float(p.stok_terkini or 0),
            "stok_minimal": float(p.stok_minimal or 0),
            "is_active": bool(p.is_active),
        }
        for p in produk_list
    ]

    ctx = build_shell_context(
        user, db=db, current_path="/web/master/produk",
        page_subtitle="Master Produk",
        data=data, total=len(data),
        q=q, tipe=tipe, only_active=only_active_bool,
        tipes=_VALID_TIPE_PRODUK,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_produk_list.html", ctx)


@router.get("/master/produk/tambah", response_class=HTMLResponse)
def master_produk_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    ctx = build_shell_context(
        user, db=db, current_path="/web/master/produk",
        page_subtitle="Tambah Produk Baru",
        form={}, tipes=_VALID_TIPE_PRODUK, error=None,
        is_edit=False,
    )
    return templates.TemplateResponse(request, "master_produk_form.html", ctx)


@router.post("/master/produk/tambah", response_class=HTMLResponse)
def master_produk_tambah_submit(
    request: Request, db: DbSession,
    kode_produk: str = Form(...),
    nama_produk: str = Form(...),
    tipe_produk: str = Form(...),
    satuan: str = Form(...),
    harga_jual: float = Form(..., ge=0),
    stok_terkini: float = Form(default=0, ge=0),
    stok_minimal: float = Form(default=5, ge=0),
    # Produk topikal: kandungan (boleh tampil) + nama_dagang (merk asli, internal)
    kandungan: str = Form(default=""),
    nama_dagang: str = Form(default=""),
    # TODO-NEW-3 #31 — auto-fill cara pakai resep SOAP (opsional)
    default_cara_pakai: str = Form(default=""),
    # DEC-060 Komisi Hybrid Produk (single dokter)
    hpp_per_unit: float = Form(default=0, ge=0),
    pajak_persen: float = Form(default=0, ge=0),
    pajak_nominal: float = Form(default=0, ge=0),
    komisi_dokter_tipe: str = Form(default=""),
    komisi_dokter_value: float = Form(default=0, ge=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        dcp_clean = (default_cara_pakai or "").strip()
        payload = MasterProdukCreate(
            kode_produk=kode_produk.strip(),
            nama_produk=nama_produk.strip(),
            tipe_produk=tipe_produk,
            satuan=satuan.strip(),
            harga_jual=Decimal(str(harga_jual)),
            stok_terkini=stok_terkini,
            stok_minimal=stok_minimal,
            kandungan=(kandungan.strip() or None),
            nama_dagang=(nama_dagang.strip() or None),
            default_cara_pakai=(dcp_clean if dcp_clean else None),
            hpp_per_unit=Decimal(str(hpp_per_unit)),
            pajak_persen=Decimal(str(pajak_persen)),
            pajak_nominal=(Decimal(str(pajak_nominal)) if pajak_nominal > 0 else None),
            komisi_dokter_tipe=(komisi_dokter_tipe or None),
            komisi_dokter_value=Decimal(str(komisi_dokter_value)),
        )
        created = MasterProdukService(db).create_produk(
            payload=payload, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/produk?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/produk?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/produk?ok={quote(f'Produk {created.nama_produk} berhasil dibuat.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/master/produk/{id_produk}", response_class=HTMLResponse)
def master_produk_edit_form(id_produk: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        p = MasterProdukService(db).get_by_id(id_produk)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)

    form = {
        "id_produk": p.id_produk,
        "kode_produk": p.kode_produk,
        "nama_produk": p.nama_produk,
        "tipe_produk": p.tipe_produk,
        "satuan": p.satuan,
        "harga_jual": float(p.harga_jual),
        "stok_terkini": float(p.stok_terkini or 0),
        "stok_minimal": float(p.stok_minimal or 0),
        "is_active": bool(p.is_active),
        # Produk topikal: kandungan (boleh tampil) + nama_dagang (merk asli, internal)
        "kandungan": p.kandungan or "",
        "nama_dagang": p.nama_dagang or "",
        # TODO-NEW-3 #31 — auto-fill cara pakai resep SOAP
        "default_cara_pakai": p.default_cara_pakai or "",
        # DEC-060 Komisi Hybrid Produk
        "hpp_per_unit": float(p.hpp_per_unit or 0),
        "pajak_persen": float(p.pajak_persen or 0),
        "pajak_nominal": float(p.pajak_nominal or 0),
        "komisi_dokter_tipe": p.komisi_dokter_tipe or "",
        "komisi_dokter_value": float(p.komisi_dokter_value or 0),
    }
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/produk",
        page_subtitle=f"Edit Produk - {p.nama_produk}",
        form=form, tipes=_VALID_TIPE_PRODUK,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
        is_edit=True,
    )
    return templates.TemplateResponse(request, "master_produk_form.html", ctx)


@router.post("/master/produk/{id_produk}", response_class=HTMLResponse)
def master_produk_edit_submit(
    id_produk: int, request: Request, db: DbSession,
    kode_produk: str = Form(...),
    nama_produk: str = Form(...),
    tipe_produk: str = Form(...),
    satuan: str = Form(...),
    harga_jual: float = Form(..., ge=0),
    stok_minimal: float = Form(..., ge=0),
    # Produk topikal: kandungan (boleh tampil) + nama_dagang (merk asli, internal)
    kandungan: str = Form(default=""),
    nama_dagang: str = Form(default=""),
    # TODO-NEW-3 #31 — auto-fill cara pakai resep SOAP (opsional)
    default_cara_pakai: str = Form(default=""),
    # DEC-060 Komisi Hybrid Produk
    hpp_per_unit: float = Form(default=0, ge=0),
    pajak_persen: float = Form(default=0, ge=0),
    pajak_nominal: float = Form(default=0, ge=0),
    komisi_dokter_tipe: str = Form(default=""),
    komisi_dokter_value: float = Form(default=0, ge=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        # Normalize default_cara_pakai: "" → None (clear field)
        dcp_clean = (default_cara_pakai or "").strip()
        payload = MasterProdukUpdate(
            kode_produk=kode_produk.strip(),
            nama_produk=nama_produk.strip(),
            tipe_produk=tipe_produk,
            satuan=satuan.strip(),
            harga_jual=Decimal(str(harga_jual)),
            stok_minimal=stok_minimal,
            kandungan=(kandungan.strip() or None),
            nama_dagang=(nama_dagang.strip() or None),
            default_cara_pakai=(dcp_clean if dcp_clean else None),
            hpp_per_unit=Decimal(str(hpp_per_unit)),
            pajak_persen=Decimal(str(pajak_persen)),
            pajak_nominal=(Decimal(str(pajak_nominal)) if pajak_nominal > 0 else None),
            komisi_dokter_tipe=(komisi_dokter_tipe or None),
            komisi_dokter_value=Decimal(str(komisi_dokter_value)),
        )
        MasterProdukService(db).update_profile(
            id_produk=id_produk, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/produk/{id_produk}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/produk/{id_produk}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/produk?ok={quote('Produk berhasil diupdate.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/produk/{id_produk}/toggle-active")
def master_produk_toggle_active(
    id_produk: int, request: Request, db: DbSession,
    is_active: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    new_state = is_active == "1"
    try:
        MasterProdukService(db).set_active(
            id_produk=id_produk, is_active=new_state,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/produk?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    label = "diaktifkan" if new_state else "dinonaktifkan"
    return RedirectResponse(
        url=f"/web/master/produk?ok={quote(f'Produk berhasil {label}.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# NOTE: Route POST /master/produk/{id}/restock dihapus per DEC-040.
# Semua restock wajib lewat modul Pengadaan (PO + Receive) untuk audit trail.
# Untuk koreksi stok, pakai Stock Opname.
# Backend MasterProdukService.restock() tetap di-keep untuk dipanggil internal
# oleh PemesananService.receive_item().


# =============================================================================
# MASTER BAHAN KLINIK (inventory_stok)
# =============================================================================
@router.get("/master/bahan", response_class=HTMLResponse)
def master_bahan_list(request: Request, db: DbSession, q: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        bahan_list = InventoryRepository(db).list_all(keyword=q or None, limit=500)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    data = [
        {
            "id_bahan": b.id_bahan,
            "nama_bahan": b.nama_bahan,
            "stok_gudang_utama": float(b.stok_gudang_utama or 0),
            "stok_kabin": float(b.stok_kabin or 0),
            "satuan": b.satuan or "-",
            "satuan_pembelian": b.satuan_pembelian or "-",
            "rasio_konversi": float(b.rasio_konversi or 1),
        }
        for b in bahan_list
    ]
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/bahan",
        page_subtitle="Master Bahan Klinik",
        data=data, total=len(data), q=q,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_bahan_list.html", ctx)


@router.get("/master/bahan/tambah", response_class=HTMLResponse)
def master_bahan_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/bahan",
        page_subtitle="Tambah Bahan Klinik",
        form={}, error=None, is_edit=False,
    )
    return templates.TemplateResponse(request, "master_bahan_form.html", ctx)


@router.post("/master/bahan/tambah", response_class=HTMLResponse)
def master_bahan_tambah_submit(
    request: Request, db: DbSession,
    nama_bahan: str = Form(...),
    satuan: str = Form(default=""),
    satuan_pembelian: str = Form(default=""),
    rasio_konversi: float = Form(default=1.0, gt=0),
    stok_gudang_utama: float = Form(default=0, ge=0),
    stok_kabin: float = Form(default=0, ge=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    nama_clean = (nama_bahan or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(
            url=f"/web/master/bahan?err={quote('Nama bahan 1-100 karakter')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        bahan = InventoryStok(
            nama_bahan=nama_clean,
            satuan=satuan.strip() or None,
            satuan_pembelian=satuan_pembelian.strip() or None,
            rasio_konversi=rasio_konversi,
            stok_gudang_utama=stok_gudang_utama,
            stok_kabin=stok_kabin,
        )
        # DEC-030: service-owned transaction — service yang commit.
        created = InventoryService(db).create_bahan_with_audit(
            bahan=bahan,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/bahan?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/bahan?ok={quote(f'Bahan {created.nama_bahan} berhasil dibuat.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/master/bahan/{id_bahan}", response_class=HTMLResponse)
def master_bahan_edit_form(id_bahan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    b = InventoryRepository(db).get_stok(id_bahan)
    if b is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Bahan tidak ditemukan.</div>", status_code=404)

    form = {
        "id_bahan": b.id_bahan,
        "nama_bahan": b.nama_bahan,
        "satuan": b.satuan or "",
        "satuan_pembelian": b.satuan_pembelian or "",
        "rasio_konversi": float(b.rasio_konversi or 1),
        "stok_gudang_utama": float(b.stok_gudang_utama or 0),
        "stok_kabin": float(b.stok_kabin or 0),
    }
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/bahan",
        page_subtitle=f"Edit Bahan - {b.nama_bahan}",
        form=form, is_edit=True,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_bahan_form.html", ctx)


@router.post("/master/bahan/{id_bahan}", response_class=HTMLResponse)
def master_bahan_edit_submit(
    id_bahan: int, request: Request, db: DbSession,
    nama_bahan: str = Form(...),
    satuan: str = Form(default=""),
    satuan_pembelian: str = Form(default=""),
    rasio_konversi: float = Form(default=1.0, gt=0),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    nama_clean = (nama_bahan or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(
            url=f"/web/master/bahan/{id_bahan}?err={quote('Nama bahan 1-100 karakter')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        b = InventoryRepository(db).get_stok(id_bahan)
        if b is None:
            raise HTTPException(404, "Bahan tidak ditemukan")
        data_lama = {
            "nama_bahan": b.nama_bahan,
            "satuan": b.satuan,
            "satuan_pembelian": b.satuan_pembelian,
            "rasio_konversi": float(b.rasio_konversi or 1),
        }
        update_data = {
            "nama_bahan": nama_clean,
            "satuan": satuan.strip() or None,
            "satuan_pembelian": satuan_pembelian.strip() or None,
            "rasio_konversi": rasio_konversi,
        }
        # DEC-030: service-owned transaction — service yang commit.
        InventoryService(db).update_bahan_with_audit(
            bahan=b,
            data_lama=data_lama,
            update_data=update_data,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/bahan/{id_bahan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/bahan/{id_bahan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/bahan?ok={quote('Bahan berhasil diupdate.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TREATMENT KOMPONEN (link bahan/alat ke treatment)
# =============================================================================
@router.post("/master/treatment/{id_treatment}/komponen/tambah")
def treatment_komponen_tambah(
    id_treatment: int, request: Request, db: DbSession,
    kategori: str = Form(...),
    id_bahan: int = Form(..., ge=1),
    qty: float = Form(..., gt=0),
    satuan: str = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        kategori_enum = KategoriKomponenTreatmentEnum(kategori.upper())
    except ValueError:
        return RedirectResponse(
            url=f"/web/master/treatment/{id_treatment}?err={quote('Kategori harus BAHAN atau ALAT')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # DEC-030: service-owned transaction — service yang commit + audit.
        komponen = MasterTreatmentService(db).tambah_komponen(
            id_treatment=id_treatment,
            kategori=kategori_enum,
            id_bahan=id_bahan,
            qty=qty,
            satuan=satuan,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/treatment/{id_treatment}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/treatment/{id_treatment}?ok={quote('Komponen ditambahkan.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/treatment/{id_treatment}/komponen/{id_komponen}/hapus")
def treatment_komponen_hapus(
    id_treatment: int, id_komponen: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()

    try:
        MasterTreatmentService(db).hapus_komponen(
            id_komponen=id_komponen,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/treatment/{id_treatment}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/master/treatment/{id_treatment}?ok={quote('Komponen dihapus.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# #362A - Master Membership CRUD
# =============================================================================
@router.get("/master/membership", response_class=HTMLResponse)
def master_membership_list(
    request: Request, db: DbSession,
    keyword: str = "",
    only_active: str = "",  # "" | "1"
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    tiers = MasterMembershipService(db).list_all(
        keyword=(keyword.strip() or None),
        only_active=(only_active == "1"),
        limit=500,
    )
    rows = []
    for t in tiers:
        rows.append({
            "id_membership": t.id_membership,
            "nama_tier": t.nama_tier,
            "harga_aktivasi": float(t.harga_aktivasi or 0),
            "durasi_bulan": int(t.durasi_bulan or 0),
            "free_konsultasi_dokter": bool(t.free_konsultasi_dokter),
            "diskon_treatment_persen": float(t.diskon_treatment_persen or 0),
            "diskon_produk_persen": float(t.diskon_produk_persen or 0),
            "is_active": bool(t.is_active),
            "urutan_tampilan": int(t.urutan_tampilan or 0),
            "catatan": t.catatan or "",
        })
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/membership",
        page_subtitle=f"Master Membership ({len(rows)} tier)",
        rows=rows, keyword=keyword, only_active_selected=(only_active == "1"),
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_membership_list.html", ctx)


@router.get("/master/membership/tambah", response_class=HTMLResponse)
def master_membership_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/membership",
        page_subtitle="Tambah Tier Membership",
        form={}, is_edit=False, error=None,
    )
    return templates.TemplateResponse(request, "master_membership_form.html", ctx)


@router.post("/master/membership/tambah", response_class=HTMLResponse)
def master_membership_tambah_submit(
    request: Request, db: DbSession,
    nama_tier: str = Form(...),
    harga_aktivasi: float = Form(default=0, ge=0),
    durasi_bulan: int = Form(default=12, ge=1, le=120),
    free_konsultasi_dokter: int = Form(default=0),
    diskon_treatment_persen: float = Form(default=0, ge=0, le=100),
    diskon_produk_persen: float = Form(default=0, ge=0, le=100),
    urutan_tampilan: int = Form(default=0, ge=0),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        payload = MasterMembershipCreate(
            nama_tier=nama_tier.strip(),
            harga_aktivasi=Decimal(str(harga_aktivasi)),
            durasi_bulan=durasi_bulan,
            free_konsultasi_dokter=bool(free_konsultasi_dokter),
            diskon_treatment_persen=Decimal(str(diskon_treatment_persen)),
            diskon_produk_persen=Decimal(str(diskon_produk_persen)),
            urutan_tampilan=urutan_tampilan,
            catatan=(catatan or "").strip() or None,
        )
        created = MasterMembershipService(db).create_tier(
            payload=payload, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/membership?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership?ok={quote(f'Tier {created.nama_tier} berhasil dibuat.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/master/membership/{id_membership}", response_class=HTMLResponse)
def master_membership_edit_form(id_membership: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        t = MasterMembershipService(db).get_by_id(id_membership)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    form = {
        "id_membership": t.id_membership,
        "nama_tier": t.nama_tier,
        "harga_aktivasi": float(t.harga_aktivasi or 0),
        "durasi_bulan": int(t.durasi_bulan or 12),
        "free_konsultasi_dokter": bool(t.free_konsultasi_dokter),
        "diskon_treatment_persen": float(t.diskon_treatment_persen or 0),
        "diskon_produk_persen": float(t.diskon_produk_persen or 0),
        "urutan_tampilan": int(t.urutan_tampilan or 0),
        "catatan": t.catatan or "",
        "is_active": bool(t.is_active),
    }
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/membership",
        page_subtitle=f"Edit Tier - {t.nama_tier}",
        form=form, is_edit=True,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_membership_form.html", ctx)


@router.post("/master/membership/{id_membership}", response_class=HTMLResponse)
def master_membership_edit_submit(
    id_membership: int, request: Request, db: DbSession,
    nama_tier: str = Form(...),
    harga_aktivasi: float = Form(default=0, ge=0),
    durasi_bulan: int = Form(default=12, ge=1, le=120),
    free_konsultasi_dokter: int = Form(default=0),
    diskon_treatment_persen: float = Form(default=0, ge=0, le=100),
    diskon_produk_persen: float = Form(default=0, ge=0, le=100),
    urutan_tampilan: int = Form(default=0, ge=0),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        catatan_clean = (catatan or "").strip()
        payload = MasterMembershipUpdate(
            nama_tier=nama_tier.strip(),
            harga_aktivasi=Decimal(str(harga_aktivasi)),
            durasi_bulan=durasi_bulan,
            free_konsultasi_dokter=bool(free_konsultasi_dokter),
            diskon_treatment_persen=Decimal(str(diskon_treatment_persen)),
            diskon_produk_persen=Decimal(str(diskon_produk_persen)),
            urutan_tampilan=urutan_tampilan,
            catatan=(catatan_clean if catatan_clean else None),
        )
        MasterMembershipService(db).update_tier(
            id_membership=id_membership, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership?ok={quote('Tier berhasil diupdate.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/membership/{id_membership}/toggle-active", response_class=HTMLResponse)
def master_membership_toggle_active(
    id_membership: int, request: Request, db: DbSession,
    is_active: int = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        MasterMembershipService(db).set_active(
            id_membership=id_membership,
            is_active=bool(is_active),
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/membership?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership?ok={quote('Status tier berhasil diubah.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# #362B-B - Master Membership Benefit Treatment CRUD
# =============================================================================
@router.get("/master/membership/{id_membership}/benefit", response_class=HTMLResponse)
def master_membership_benefit_list(id_membership: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        tier = MasterMembershipService(db).get_by_id(id_membership)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    benefits = MembershipBenefitService(db).list_by_tier(id_membership)
    # Active treatments untuk dropdown tambah
    from app.repositories.treatment_repo import TreatmentRepository
    all_treatments = TreatmentRepository(db).list_master_active(limit=500)
    treatments_dropdown = [
        {"id_treatment": t.id_treatment, "nama_treatment": t.nama_treatment, "harga": float(t.harga or 0)}
        for t in all_treatments
    ]
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/membership",
        page_subtitle=f"Benefit - {tier.nama_tier}",
        tier={
            "id_membership": tier.id_membership,
            "nama_tier": tier.nama_tier,
            "harga_aktivasi": float(tier.harga_aktivasi or 0),
            "durasi_bulan": tier.durasi_bulan,
        },
        benefits=benefits,
        treatments_dropdown=treatments_dropdown,
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_membership_benefit.html", ctx)


@router.post("/master/membership/{id_membership}/benefit/tambah", response_class=HTMLResponse)
def master_membership_benefit_tambah(
    id_membership: int, request: Request, db: DbSession,
    id_treatment: int = Form(...),
    kuota_total: int = Form(..., ge=1, le=1000),
    periode_kuota: str = Form(...),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    from app.db.models import PeriodeKuotaEnum
    try:
        periode_enum = PeriodeKuotaEnum(periode_kuota.strip().upper())
    except ValueError:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err=Periode%20kuota%20tidak%20valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = BenefitTreatmentCreate(
            id_membership=id_membership,
            id_treatment=id_treatment,
            kuota_total=kuota_total,
            periode_kuota=periode_enum,
            catatan=(catatan or "").strip() or None,
        )
        MembershipBenefitService(db).create_benefit(
            payload=payload, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership/{id_membership}/benefit?ok={quote('Benefit ditambahkan.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/membership/{id_membership}/benefit/{id_benefit}/edit", response_class=HTMLResponse)
def master_membership_benefit_edit(
    id_membership: int, id_benefit: int, request: Request, db: DbSession,
    kuota_total: int = Form(..., ge=1, le=1000),
    periode_kuota: str = Form(...),
    catatan: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    from app.db.models import PeriodeKuotaEnum
    try:
        periode_enum = PeriodeKuotaEnum(periode_kuota.strip().upper())
    except ValueError:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err=Periode%20tidak%20valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = BenefitTreatmentUpdate(
            kuota_total=kuota_total,
            periode_kuota=periode_enum,
            catatan=(catatan or "").strip() or None,
        )
        MembershipBenefitService(db).update_benefit(
            id_benefit=id_benefit, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership/{id_membership}/benefit?ok={quote('Benefit diupdate.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/master/membership/{id_membership}/benefit/{id_benefit}/toggle-active", response_class=HTMLResponse)
def master_membership_benefit_toggle(
    id_membership: int, id_benefit: int, request: Request, db: DbSession,
    is_active: int = Form(...),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_master_data_role(user):
        return _403()
    try:
        MembershipBenefitService(db).set_active(
            id_benefit=id_benefit, is_active=bool(is_active),
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/master/membership/{id_membership}/benefit?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/master/membership/{id_membership}/benefit?ok={quote('Status benefit diubah.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# MASTER DISTRIBUTOR (P-L1) — CRUD
# =============================================================================
@router.get("/master/distributor", response_class=HTMLResponse)
def master_distributor_list(request: Request, db: DbSession, q: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    from app.db.models import MasterDistributor
    query = db.query(MasterDistributor)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(MasterDistributor.nama.ilike(like))
    rows = query.order_by(MasterDistributor.is_active.desc(), MasterDistributor.nama).limit(500).all()
    data = [
        {"id_distributor": d.id_distributor, "nama": d.nama, "telepon": d.telepon or "-",
         "alamat": d.alamat or "-", "kontak_person": d.kontak_person or "-", "is_active": d.is_active}
        for d in rows
    ]
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/distributor",
        page_subtitle="Master Distributor", data=data, total=len(data), q=q,
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_distributor_list.html", ctx)


@router.get("/master/distributor/tambah", response_class=HTMLResponse)
def master_distributor_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/distributor",
        page_subtitle="Tambah Distributor", form={}, is_edit=False,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_distributor_form.html", ctx)


@router.post("/master/distributor/tambah", response_class=HTMLResponse)
def master_distributor_tambah_submit(
    request: Request, db: DbSession,
    nama: str = Form(...),
    alamat: str = Form(default=""),
    telepon: str = Form(default=""),
    email: str = Form(default=""),
    kontak_person: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    from app.db.models import MasterDistributor
    nama_clean = (nama or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(url=f"/web/master/distributor?err={quote('Nama 1-100 karakter')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        d = MasterDistributor(
            nama=nama_clean, alamat=alamat.strip() or None, telepon=telepon.strip() or None,
            email=email.strip() or None, kontak_person=kontak_person.strip() or None,
        )
        db.add(d)
        db.flush()
        AuditService(db).log_create(id_staf=user.id_staf, tabel="master_distributor",
                                    id_target=d.id_distributor, data_baru={"nama": nama_clean}, request=request)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/web/master/distributor?err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/distributor?ok={quote(f'Distributor {nama_clean} dibuat.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/master/distributor/{id_distributor}", response_class=HTMLResponse)
def master_distributor_edit_form(id_distributor: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    from app.db.models import MasterDistributor
    d = db.get(MasterDistributor, id_distributor)
    if d is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Distributor tidak ditemukan.</div>", status_code=404)
    form = {
        "id_distributor": d.id_distributor, "nama": d.nama, "alamat": d.alamat or "",
        "telepon": d.telepon or "", "email": d.email or "", "kontak_person": d.kontak_person or "",
        "is_active": d.is_active,
    }
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/distributor",
        page_subtitle=f"Edit Distributor - {d.nama}", form=form, is_edit=True,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_distributor_form.html", ctx)


@router.post("/master/distributor/{id_distributor}", response_class=HTMLResponse)
def master_distributor_edit_submit(
    id_distributor: int, request: Request, db: DbSession,
    nama: str = Form(...),
    alamat: str = Form(default=""),
    telepon: str = Form(default=""),
    email: str = Form(default=""),
    kontak_person: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    from app.db.models import MasterDistributor
    d = db.get(MasterDistributor, id_distributor)
    if d is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Distributor tidak ditemukan.</div>", status_code=404)
    nama_clean = (nama or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(url=f"/web/master/distributor/{id_distributor}?err={quote('Nama 1-100 karakter')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        d.nama = nama_clean
        d.alamat = alamat.strip() or None
        d.telepon = telepon.strip() or None
        d.email = email.strip() or None
        d.kontak_person = kontak_person.strip() or None
        AuditService(db).log(aksi="UPDATE", id_staf=user.id_staf, tabel_target="master_distributor",
                             id_target=id_distributor, keterangan="Edit distributor", request=request)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/web/master/distributor/{id_distributor}?err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/distributor?ok={quote(f'Distributor {nama_clean} diperbarui.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/distributor/{id_distributor}/toggle", response_class=HTMLResponse)
def master_distributor_toggle(id_distributor: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_master_data_role(user) or require_purchasing_full_role(user)):
        return _403()
    from app.db.models import MasterDistributor
    d = db.get(MasterDistributor, id_distributor)
    if d is None:
        return HTMLResponse("<div style='padding:2rem'>404</div>", status_code=404)
    d.is_active = not d.is_active
    AuditService(db).log(aksi="UPDATE", id_staf=user.id_staf, tabel_target="master_distributor",
                         id_target=id_distributor, keterangan=f"Set aktif={d.is_active}", request=request)
    db.commit()
    return RedirectResponse(url=f"/web/master/distributor?ok={quote('Status distributor diubah.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


# =============================================================================
# MASTER LOKASI PENGIRIMAN (ship-to) — SHIP-L2
# =============================================================================
def _lok_guard(user):
    return require_master_data_role(user) or require_purchasing_full_role(user)


@router.get("/master/lokasi-pengiriman", response_class=HTMLResponse)
def master_lokasi_list(request: Request, db: DbSession, q: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    from app.db.models import LokasiPengiriman
    query = db.query(LokasiPengiriman)
    if q and q.strip():
        query = query.filter(LokasiPengiriman.nama.ilike(f"%{q.strip()}%"))
    rows = query.order_by(LokasiPengiriman.is_active.desc(), LokasiPengiriman.is_default.desc(),
                          LokasiPengiriman.nama).limit(500).all()
    data = [
        {"id_lokasi": r.id_lokasi, "nama": r.nama, "alamat": r.alamat or "-",
         "telepon": r.telepon or "-", "kontak_person": r.kontak_person or "-",
         "is_default": r.is_default, "is_active": r.is_active}
        for r in rows
    ]
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/lokasi-pengiriman",
        page_subtitle="Master Lokasi Pengiriman", data=data, total=len(data), q=q,
        flash=request.query_params.get("ok"), error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_lokasi_list.html", ctx)


@router.get("/master/lokasi-pengiriman/tambah", response_class=HTMLResponse)
def master_lokasi_tambah_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/lokasi-pengiriman",
        page_subtitle="Tambah Lokasi Pengiriman", form={}, is_edit=False,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_lokasi_form.html", ctx)


def _lok_set_default(db, id_lokasi):
    from app.db.models import LokasiPengiriman
    db.query(LokasiPengiriman).filter(LokasiPengiriman.id_lokasi != id_lokasi).update(
        {LokasiPengiriman.is_default: False}
    )


@router.post("/master/lokasi-pengiriman/tambah", response_class=HTMLResponse)
def master_lokasi_tambah_submit(
    request: Request, db: DbSession,
    nama: str = Form(...),
    alamat: str = Form(default=""),
    telepon: str = Form(default=""),
    kontak_person: str = Form(default=""),
    is_default: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    from app.db.models import LokasiPengiriman
    nama_clean = (nama or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(url=f"/web/master/lokasi-pengiriman?err={quote('Nama 1-100 karakter')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        r = LokasiPengiriman(
            nama=nama_clean, alamat=alamat.strip() or None, telepon=telepon.strip() or None,
            kontak_person=kontak_person.strip() or None, is_default=(is_default == "1"),
        )
        db.add(r)
        db.flush()
        if r.is_default:
            _lok_set_default(db, r.id_lokasi)
        AuditService(db).log_create(id_staf=user.id_staf, tabel="lokasi_pengiriman",
                                    id_target=r.id_lokasi, data_baru={"nama": nama_clean}, request=request)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/web/master/lokasi-pengiriman?err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/lokasi-pengiriman?ok={quote(f'Lokasi {nama_clean} dibuat.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.get("/master/lokasi-pengiriman/{id_lokasi}", response_class=HTMLResponse)
def master_lokasi_edit_form(id_lokasi: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    from app.db.models import LokasiPengiriman
    r = db.get(LokasiPengiriman, id_lokasi)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Lokasi tidak ditemukan.</div>", status_code=404)
    form = {"id_lokasi": r.id_lokasi, "nama": r.nama, "alamat": r.alamat or "",
            "telepon": r.telepon or "", "kontak_person": r.kontak_person or "",
            "is_default": r.is_default, "is_active": r.is_active}
    ctx = build_shell_context(
        user, db=db, current_path="/web/master/lokasi-pengiriman",
        page_subtitle=f"Edit Lokasi - {r.nama}", form=form, is_edit=True,
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "master_lokasi_form.html", ctx)


@router.post("/master/lokasi-pengiriman/{id_lokasi}", response_class=HTMLResponse)
def master_lokasi_edit_submit(
    id_lokasi: int, request: Request, db: DbSession,
    nama: str = Form(...),
    alamat: str = Form(default=""),
    telepon: str = Form(default=""),
    kontak_person: str = Form(default=""),
    is_default: str = Form(default=""),
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    from app.db.models import LokasiPengiriman
    r = db.get(LokasiPengiriman, id_lokasi)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404 - Lokasi tidak ditemukan.</div>", status_code=404)
    nama_clean = (nama or "").strip()
    if not nama_clean or len(nama_clean) > 100:
        return RedirectResponse(url=f"/web/master/lokasi-pengiriman/{id_lokasi}?err={quote('Nama 1-100 karakter')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    try:
        r.nama = nama_clean
        r.alamat = alamat.strip() or None
        r.telepon = telepon.strip() or None
        r.kontak_person = kontak_person.strip() or None
        r.is_default = (is_default == "1")
        db.flush()
        if r.is_default:
            _lok_set_default(db, r.id_lokasi)
        AuditService(db).log(aksi="UPDATE", id_staf=user.id_staf, tabel_target="lokasi_pengiriman",
                             id_target=id_lokasi, keterangan="Edit lokasi pengiriman", request=request)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/web/master/lokasi-pengiriman/{id_lokasi}?err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/master/lokasi-pengiriman?ok={quote(f'Lokasi {nama_clean} diperbarui.')}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.post("/master/lokasi-pengiriman/{id_lokasi}/toggle", response_class=HTMLResponse)
def master_lokasi_toggle(id_lokasi: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _lok_guard(user):
        return _403()
    from app.db.models import LokasiPengiriman
    r = db.get(LokasiPengiriman, id_lokasi)
    if r is None:
        return HTMLResponse("<div style='padding:2rem'>404</div>", status_code=404)
    r.is_active = not r.is_active
    AuditService(db).log(aksi="UPDATE", id_staf=user.id_staf, tabel_target="lokasi_pengiriman",
                         id_target=id_lokasi, keterangan=f"Set aktif={r.is_active}", request=request)
    db.commit()
    return RedirectResponse(url=f"/web/master/lokasi-pengiriman?ok={quote('Status lokasi diubah.')}",
                            status_code=status.HTTP_303_SEE_OTHER)
