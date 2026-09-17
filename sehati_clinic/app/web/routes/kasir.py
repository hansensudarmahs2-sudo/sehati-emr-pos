"""
Kasir web routes:
- GET /web/kasir/antrian                            - page shell
- GET /web/kasir/antrian/list                       - HTMX partial (auto-refresh 10s)
- GET /web/kasir/tagihan/{id_kunjungan}             - detail tagihan + form bayar
- POST /web/kasir/tagihan/{id_kunjungan}/bayar      - submit pembayaran → redirect ke sukses
- GET /web/kasir/bayar/sukses/{id_transaksi}        - confirmation page + auto-print
- POST /web/kasir/tagihan/{id_kunjungan}/void       - void item resep (PIN auth)
- GET /web/kasir/_pembayaran-row                    - HTMX partial: 1 row pembayaran
- GET /web/kasir/nota/{id_transaksi}/cetak          - render nota pembayaran (A5/thermal)

Role gate: Kasir + Admin + Owner + Superadmin.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.schemas.kasir import (
    BayarRequest,
    PembayaranItem,
    VoidItemRequest,
)
from app.services.kasir_service import KasirService
from app.services.membership_service import MembershipService
from app.services.klinik_config_service import KlinikConfigService
from app.services.print_service import PrintService
from app.db.models import StafRoleEnum
from app.web.routes._shared import (
    render_cached,
    build_shell_context,
    get_user_from_cookie,
    require_kasir_role,
    templates,
)


router = APIRouter(tags=["Web Kasir"])


# =============================================================================
# GET /web/kasir/antrian - page shell
# =============================================================================
@router.get("/kasir/antrian", response_class=HTMLResponse)
def kasir_antrian_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Kasir/Admin/Owner.</div>", status_code=403)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kasir",
        page_subtitle="Antri Bayar Hari Ini",
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "kasir_antrian.html", ctx)


# =============================================================================
# GET /web/kasir/antrian/list - HTMX partial
# =============================================================================
@router.get("/kasir/antrian/list", response_class=HTMLResponse)
def kasir_antrian_partial(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Sesi habis.</div>", status_code=401)
    if not require_kasir_role(user):
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>403</div>", status_code=403)

    def _build():
        antrian_resp = KasirService(db).lihat_antrian()
        antrian_dict = antrian_resp.model_dump()
        return templates.TemplateResponse(request, "_kasir_antrian_content.html", {"antrian": antrian_dict})
    try:
        # CACHE tampilan (KESTABILAN §9): antrian kasir sama utk semua kasir (shared key).
        from app.core.ttl_cache import ANTRIAN_TTL
        return render_cached("antrian:kasir", ANTRIAN_TTL, _build)
    except Exception as e:
        return HTMLResponse(f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Error: {e!s}</div>", status_code=500)


# =============================================================================
# GET /web/kasir/tagihan/{id_kunjungan} - detail + form bayar
# =============================================================================
@router.get("/kasir/tagihan/{id_kunjungan}", response_class=HTMLResponse)
def kasir_tagihan_page(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    try:
        # Phase 7: pass user_role untuk compute force-void eligibility
        tagihan_resp = KasirService(db).get_tagihan(id_kunjungan, user_role=user.role)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    except Exception as e:
        return HTMLResponse(f"<div style='padding:2rem'>Error: {e!s}</div>", status_code=500)

    tagihan_dict = tagihan_resp.model_dump()

    # P0-2: token idempotency per-render form Bayar. Double-click/retry kirim token
    # sama → ditolak backstop UNIQUE di proses_bayar. Split billing = render baru = token baru.
    import secrets as _secrets
    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kasir",
        page_subtitle=f"Tagihan - {tagihan_dict.get('nama_pasien', '-')}",
        tagihan=tagihan_dict,
        idempotency_key=_secrets.token_urlsafe(24),
        flash=request.query_params.get("ok"),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "kasir_tagihan.html", ctx)


# =============================================================================
# GET /web/kasir/_pembayaran-row - HTMX partial: 1 row pembayaran
# =============================================================================
@router.get("/kasir/_pembayaran-row", response_class=HTMLResponse)
def kasir_pembayaran_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    return templates.TemplateResponse(request, "_pembayaran_row.html", {})


# =============================================================================
# POST /web/kasir/tagihan/{id_kunjungan}/bayar - submit pembayaran
# =============================================================================
@router.post("/kasir/tagihan/{id_kunjungan}/bayar", response_class=HTMLResponse)
async def kasir_bayar(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    form_data = await request.form()
    metode_list = form_data.getlist("metode_bayar")
    nominal_list = form_data.getlist("nominal")
    keterangan_promo = (form_data.get("keterangan_promo") or "").strip()
    idempotency_key = (form_data.get("idempotency_key") or "").strip() or None  # P0-2

    pembayaran_items = []
    for i, metode in enumerate(metode_list):
        metode_str = (metode or "").strip().upper()
        if not metode_str:
            continue
        try:
            nominal = Decimal(str(nominal_list[i] if i < len(nominal_list) else 0))
        except Exception:
            continue
        if nominal <= 0:
            continue
        try:
            pembayaran_items.append(PembayaranItem(metode_bayar=metode_str, nominal=nominal))
        except Exception as e:
            from urllib.parse import quote
            return RedirectResponse(
                url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(f'Pembayaran invalid: {e!s}')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    # DEC-049: Boleh pembayaran kosong KALAU total_tagihan = 0 (series lunas).
    # Kasir tahu dari halaman tagihan (Selesaikan button tanpa form pembayaran).
    # Backend re-validate total_tagihan di server (anti-fraud), bukan trust frontend.
    if not pembayaran_items:
        # Cek dulu total tagihan — kalau Rp 0 (series), boleh lanjut tanpa pembayaran.
        # Kalau > 0, tolak dengan error normal.
        try:
            tagihan_check = KasirService(db).get_tagihan(id_kunjungan)
            total_check = float(tagihan_check.ringkasan_biaya.total_tagihan)
        except Exception:
            total_check = -1.0  # gagal cek → tolak defensive
        if total_check > 0:
            from urllib.parse import quote
            return RedirectResponse(
                url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote('Minimal 1 metode pembayaran wajib diisi.')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    try:
        payload = BayarRequest(
            id_kunjungan=id_kunjungan,
            pembayaran=pembayaran_items,
            keterangan_promo=keterangan_promo,
            idempotency_key=idempotency_key,
        )
        result = KasirService(db).proses_bayar(
            payload=payload,
            id_staf_kasir=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    data = result.get("data", {}) if isinstance(result, dict) else {}
    id_trx = data.get("id_transaksi")
    kembalian = data.get("kembalian", 0)
    total_bayar_actual = data.get("total_bayar", 0)
    # Redirect ke confirmation page — auto buka tab cetak nota di sana.
    if id_trx:
        return RedirectResponse(
            url=(
                f"/web/kasir/bayar/sukses/{id_trx}"
                f"?kembalian={float(kembalian)}&total_bayar={float(total_bayar_actual)}"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    # Fallback kalau id_transaksi tidak ada (defensive)
    from urllib.parse import quote
    msg = f"Pembayaran sukses. Kembalian: Rp {float(kembalian):,.0f}."
    return RedirectResponse(
        url=f"/web/kasir/antrian?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# M2 — MEMBERSHIP: bayar aktivasi (transaksi berdiri sendiri, id_kunjungan=NULL)
# =============================================================================
@router.get("/kasir/membership/{id_history}/bayar", response_class=HTMLResponse)
def kasir_bayar_membership_page(id_history: int, request: Request, db: DbSession):
    from urllib.parse import quote
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    from app.db.models import (
        PasienMembershipHistory as _PMH, Pasien as _P, MasterMembership as _MM,
    )
    hist = db.get(_PMH, id_history)
    if hist is None or hist.is_active or hist.id_transaksi_aktivasi is not None:
        return RedirectResponse(
            url="/web/kasir/antrian?err=" + quote("Membership tidak ditemukan / bukan PENDING."),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    pasien = db.get(_P, hist.id_pasien)
    tier = db.get(_MM, hist.id_membership)
    import secrets as _secrets
    ctx = build_shell_context(
        user, db=db, current_path="/web/kasir",
        page_subtitle=f"Bayar Membership - {pasien.nama if pasien else '-'}",
        mship={
            "id_history": id_history,
            "id_pasien": hist.id_pasien,
            "nama_pasien": pasien.nama if pasien else "-",
            "no_rm": pasien.no_rm if pasien else "-",
            "nama_tier": tier.nama_tier if tier else "-",
            "harga": float(tier.harga_aktivasi or 0) if tier else 0.0,
        },
        idempotency_key=_secrets.token_urlsafe(24),
        error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "kasir_bayar_membership.html", ctx)


@router.post("/kasir/membership/{id_history}/bayar", response_class=HTMLResponse)
async def kasir_bayar_membership(id_history: int, request: Request, db: DbSession):
    from urllib.parse import quote
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    form_data = await request.form()
    metode_list = form_data.getlist("metode_bayar")
    nominal_list = form_data.getlist("nominal")
    idempotency_key = (form_data.get("idempotency_key") or "").strip() or None

    pembayaran_items = []
    for i, metode in enumerate(metode_list):
        metode_str = (metode or "").strip().upper()
        if not metode_str:
            continue
        try:
            nominal = Decimal(str(nominal_list[i] if i < len(nominal_list) else 0))
        except Exception:
            continue
        if nominal <= 0:
            continue
        try:
            pembayaran_items.append(PembayaranItem(metode_bayar=metode_str, nominal=nominal))
        except Exception:
            continue

    if not pembayaran_items:
        return RedirectResponse(
            url=f"/web/kasir/membership/{id_history}/bayar?err=" + quote("Minimal 1 metode pembayaran wajib diisi."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = MembershipService(db).bayar_membership(
            id_history=id_history,
            pembayaran=pembayaran_items,
            id_staf_kasir=user.id_staf,
            request=request,
            idempotency_key=idempotency_key,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/membership/{id_history}/bayar?err=" + quote(str(e.detail)),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/kasir/membership/{id_history}/bayar?err=" + quote(f"Gagal: {e!s}"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    _id_trx = result.get("id_transaksi") if isinstance(result, dict) else None
    if _id_trx:
        return RedirectResponse(
            url=f"/web/kasir/membership/sukses/{_id_trx}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url="/web/kasir/antrian?ok=" + quote("Membership dibayar."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/kasir/membership/sukses/{id_transaksi}", response_class=HTMLResponse)
def kasir_bayar_membership_sukses(id_transaksi: int, request: Request, db: DbSession):
    from urllib.parse import quote
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    from app.db.models import (
        TransaksiKasir as _TK, Pasien as _P, MasterMembership as _MM,
    )
    trx = db.get(_TK, id_transaksi)
    if trx is None:
        return RedirectResponse(
            url="/web/kasir/antrian?err=" + quote("Transaksi tidak ditemukan."),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    pasien = db.get(_P, trx.id_pasien) if trx.id_pasien else None
    tier = db.get(_MM, trx.id_membership_aktivasi) if trx.id_membership_aktivasi else None
    ctx = build_shell_context(
        user, db=db, current_path="/web/kasir",
        page_subtitle="Pembayaran Membership Berhasil",
        sukses={
            "id_transaksi": id_transaksi,
            "id_pasien": trx.id_pasien,
            "nama_pasien": pasien.nama if pasien else "-",
            "no_rm": pasien.no_rm if pasien else "-",
            "nama_tier": tier.nama_tier if tier else "-",
            "nominal": float(trx.total_tagihan or 0),
        },
    )
    return templates.TemplateResponse(request, "kasir_bayar_membership_sukses.html", ctx)


# =============================================================================
# GET /web/kasir/bayar/sukses/{id_transaksi} - confirmation page + auto-print
# =============================================================================
@router.get("/kasir/bayar/sukses/{id_transaksi}", response_class=HTMLResponse)
def kasir_bayar_sukses(
    id_transaksi: int,
    request: Request,
    db: DbSession,
    kembalian: float = 0,
    total_bayar: float = 0,
):
    """
    Confirmation page setelah bayar sukses.
    Auto-buka tab cetak nota dengan default_paper_nota dari klinik config.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    # Fetch transaksi + pasien + klinik config
    from app.db.models import TransaksiKasir, Kunjungan, Pasien, MasterKlinikConfig
    from sqlalchemy import select
    stmt = (
        select(TransaksiKasir, Kunjungan, Pasien)
        .join(Kunjungan, TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan)
        .join(Pasien, Kunjungan.id_pasien == Pasien.id_pasien)
        .where(TransaksiKasir.id_transaksi == id_transaksi)
    )
    row = db.execute(stmt).first()
    if row is None:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>404 - Transaksi tidak ditemukan</h3>"
            f"<a href='/web/kasir/antrian'>&larr; Kembali ke Antrian</a></div>",
            status_code=404,
        )
    trx, kunjungan, pasien = row

    klinik_config = KlinikConfigService(db).get_config()
    default_paper = (klinik_config.default_paper_nota or "a5").lower()
    if default_paper not in ("a5", "thermal"):
        default_paper = "a5"

    tgl_bayar = (
        trx.waktu_bayar.strftime("%Y-%m-%d %H:%M")
        if trx.waktu_bayar else datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    # Fetch items_produk untuk modal void per-item reverse stok (#364, DEC-063)
    from app.db.models import TransaksiDetailProduk, MasterProduk
    detail_stmt = (
        select(TransaksiDetailProduk, MasterProduk)
        .join(MasterProduk, TransaksiDetailProduk.id_produk == MasterProduk.id_produk)
        .where(TransaksiDetailProduk.id_transaksi == id_transaksi)
    )
    from app.db.models import StokLot as _StokLot
    items_produk = []
    for d, p in db.execute(detail_stmt).all():
        _lots = db.execute(
            select(_StokLot).where(
                _StokLot.tipe_item == "PRODUK",
                _StokLot.id_produk == p.id_produk,
                _StokLot.lokasi == "RETAIL",
                _StokLot.status.in_(["AKTIF", "HABIS"]),
            ).order_by(_StokLot.tgl_ed.is_(None), _StokLot.tgl_ed.asc(), _StokLot.id_lot.desc())
        ).scalars().all()
        items_produk.append({
            "id_detail": d.id_detail,
            "id_produk": p.id_produk,
            "nama_produk": p.nama_produk,
            "qty": float(d.qty),
            "lots": [
                {"id_lot": l.id_lot, "batch_no": l.batch_no, "tgl_ed": l.tgl_ed,
                 "qty_sisa": float(l.qty_sisa or 0), "status": l.status}
                for l in _lots
            ],
        })

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kasir",
        page_subtitle=f"Pembayaran Berhasil - #{id_transaksi}",
        id_transaksi=id_transaksi,
        id_kunjungan=kunjungan.id_kunjungan,
        nama_pasien=pasien.nama,
        no_rm=pasien.no_rm,
        total_tagihan=float(trx.total_tagihan or 0),
        total_bayar=float(total_bayar),
        kembalian=float(kembalian),
        tgl_bayar=tgl_bayar,
        default_paper=default_paper,
        items_produk=items_produk,
    )
    return templates.TemplateResponse(request, "kasir_bayar_sukses.html", ctx)


# =============================================================================
# POST /web/kasir/tagihan/{id_kunjungan}/void - void item resep (PIN auth)
# =============================================================================
@router.post("/kasir/tagihan/{id_kunjungan}/void", response_class=HTMLResponse)
async def kasir_void(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    form_data = await request.form()
    from urllib.parse import quote

    try:
        # DEC-063 SYNC-V1: Phase 1 self-acc kasir + reason note, no PIN.
        payload = VoidItemRequest(
            id_resep=int(form_data.get("id_resep") or 0),
            reason_code=(form_data.get("reason_code") or "").strip(),
            alasan=(form_data.get("alasan") or "").strip(),
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(f'Data void invalid: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        KasirService(db).void_item_resep(
            payload=payload,
            id_staf_kasir=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/kasir/tagihan/{id_kunjungan}?err={quote(f'Gagal void: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/kasir/tagihan/{id_kunjungan}?ok={quote('Item resep berhasil di-void.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/kasir/nota/{id_transaksi}/cetak - render print nota (A5/thermal)
# =============================================================================
@router.get("/kasir/nota/{id_transaksi}/cetak", response_class=HTMLResponse)
def kasir_cetak_nota(
    id_transaksi: int,
    request: Request,
    db: DbSession,
    paper: str = "a5",
):
    """
    Render nota pembayaran untuk dicetak via browser (window.print()).
    Paper: a5 (default) | thermal.
    Audit log PRINT_NOTA ditulis di PrintService.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Kasir/Admin/Owner.</div>", status_code=403)

    paper_normalized = (paper or "a5").lower().strip()
    if paper_normalized not in ("a5", "thermal"):
        paper_normalized = "a5"

    try:
        ctx = PrintService(db).prepare_nota_context(
            id_transaksi=id_transaksi,
            paper=paper_normalized,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>{e.status_code} - Gagal Cetak</h3>"
            f"<p>{e.detail}</p>"
            f"<a href='/web/kasir/antrian'>&larr; Kembali</a></div>",
            status_code=e.status_code,
        )
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/kasir/antrian'>&larr; Kembali</a></div>",
            status_code=500,
        )

    template_name = (
        "print/nota_thermal.html"
        if paper_normalized == "thermal"
        else "print/nota_a5.html"
    )
    return templates.TemplateResponse(request, template_name, ctx)


__all__ = ["router"]

# =============================================================================
# POST /web/kasir/transaksi/{id_transaksi}/void — Kasir same-day void (#364)
# =============================================================================
@router.post("/kasir/transaksi/{id_transaksi}/void", response_class=HTMLResponse)
async def kasir_void_transaksi(
    id_transaksi: int,
    request: Request,
    db: DbSession,
    reason_code: str = Form(...),
    reason_note: str = Form(...),
    items_reverse_stok: str = Form(default=""),
):
    """Kasir void transaksi same-day. Phase 1 self-acc."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_kasir_role(user):
        return RedirectResponse(
            url="/web/kasir/antrian?err=Akses+ditolak",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Parse items_reverse_stok: "1,3,5" → [1, 3, 5]
    items_list = []
    if items_reverse_stok:
        try:
            items_list = [int(x.strip()) for x in items_reverse_stok.split(",") if x.strip()]
        except ValueError:
            items_list = []

    # P-L6b: peta batch pilihan operator per item (lot_<id_detail>) → {id_detail: id_lot}
    lot_map = {}
    if items_list:
        _f = await request.form()
        for _idd in items_list:
            _lv = _f.get(f"lot_{_idd}")
            if _lv and str(_lv).strip():
                try:
                    lot_map[_idd] = int(_lv)
                except ValueError:
                    pass

    try:
        result = KasirService(db).void_transaksi(
            id_transaksi=id_transaksi,
            reason_code=reason_code,
            reason_note=reason_note,
            items_reverse_stok=items_list,
            actor_id_staf=user.id_staf,
            request=request,
            lot_map=lot_map,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/bayar/sukses/{id_transaksi}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/kasir/bayar/sukses/{id_transaksi}?err=Gagal+void:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = f"Transaksi+%23{id_transaksi}+berhasil+di-void"
    if result.get("series_cancelled_count"):
        msg += f"+%28{result['series_cancelled_count']}+sesi+series+ter-cancel%29"
    return RedirectResponse(
        url=f"/web/kasir/antrian?ok={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/kasir/transaksi/{id_transaksi}/force-void — Admin/Superadmin/Owner (#364)
# =============================================================================
@router.post("/kasir/transaksi/{id_transaksi}/force-void", response_class=HTMLResponse)
def kasir_force_past_day_void(
    id_transaksi: int,
    request: Request,
    db: DbSession,
    reason_code: str = Form(...),
    reason_note: str = Form(...),
    items_reverse_stok: str = Form(default=""),
):
    """Admin/Superadmin/Owner force past-day void.
    Limit: Admin=3 hari, Superadmin/Owner=7 hari."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    # Role check inline — Kasir/Admin/Superadmin/Owner. Kasir limit 0 hari, others lebih banyak.
    allowed_roles = {StafRoleEnum.KASIR, StafRoleEnum.ADMIN, StafRoleEnum.SUPERADMIN, StafRoleEnum.OWNER}
    if user.role not in allowed_roles:
        return RedirectResponse(
            url="/web/kasir/antrian?err=Hanya+Kasir/Admin/Superadmin/Owner+yang+bisa+force+void",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    items_list = []
    if items_reverse_stok:
        try:
            items_list = [int(x.strip()) for x in items_reverse_stok.split(",") if x.strip()]
        except ValueError:
            items_list = []

    try:
        result = KasirService(db).force_past_day_void(
            id_transaksi=id_transaksi,
            reason_code=reason_code,
            reason_note=reason_note,
            items_reverse_stok=items_list,
            actor_id_staf=user.id_staf,
            actor_role=user.role,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/kasir/antrian?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/kasir/antrian?err=Gagal+force+void:+{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = f"Transaksi+%23{id_transaksi}+force+past-day+void+%28{result.get('days_past', 0)}d%29"
    return RedirectResponse(
        url=f"/web/kasir/antrian?ok={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/kasir/cari-transaksi", response_class=HTMLResponse)
def kasir_cari_transaksi_page(
    request: Request,
    db: DbSession,
    tgl_mulai: str = "",
    tgl_akhir: str = "",
    no_rm: str = "",
    status: str = "",
):
    """Phase 7 (#364): Halaman cari transaksi untuk Admin/Superadmin/Owner.
    Default: 7 hari terakhir + semua status.
    """
    from datetime import datetime, timedelta, date as date_cls
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=303)

    allowed_roles = {StafRoleEnum.KASIR, StafRoleEnum.ADMIN, StafRoleEnum.SUPERADMIN, StafRoleEnum.OWNER}
    if user.role not in allowed_roles:
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Kasir/Admin/Superadmin/Owner.</div>", status_code=403)

    # Default range: 7 hari terakhir
    today = datetime.now().date()
    if not tgl_akhir:
        tgl_akhir = today.isoformat()
    if not tgl_mulai:
        tgl_mulai = (today - timedelta(days=7)).isoformat()

    try:
        dt_mulai = datetime.strptime(tgl_mulai, "%Y-%m-%d")
        dt_akhir = datetime.strptime(tgl_akhir, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        dt_mulai = datetime.combine(today - timedelta(days=7), datetime.min.time())
        dt_akhir = datetime.combine(today + timedelta(days=1), datetime.min.time())

    from app.repositories.kasir_repo import KasirRepository
    rows = KasirRepository(db).list_past_day_transaksi(
        tgl_mulai=dt_mulai,
        tgl_akhir=dt_akhir,
        no_rm=no_rm.strip(),
        status_filter=status.strip(),
    )

    # Build display list dengan info eligibility force-void per row
    from app.services.kasir_service import KasirService
    max_days = KasirService._MAX_PAST_DAYS_BY_ROLE.get(user.role, 0)
    items = []
    now_check = KasirService._now_utc7()
    for trx, pasien in rows:
        days_past = 0
        can_force = False
        if trx.waktu_bayar:
            days_past = KasirService._days_past(trx.waktu_bayar, now_check)
        if trx.status_transaksi == "BAYAR" and max_days > 0:
            can_force = 0 < days_past <= max_days
        items.append({
            "id_transaksi": trx.id_transaksi,
            "id_kunjungan": trx.id_kunjungan,
            "waktu_bayar": trx.waktu_bayar,
            "no_rm": pasien.no_rm if pasien else "-",
            "nama_pasien": pasien.nama if pasien else "-",
            "total_tagihan": float(trx.total_tagihan or 0),
            "status_transaksi": trx.status_transaksi,
            "void_reason_code": trx.void_reason_code,
            "void_at": trx.void_at,
            "days_past": days_past,
            "can_force_void": can_force,
        })

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/kasir/cari-transaksi",
        page_subtitle="Cari Transaksi",
        items=items,
        total=len(items),
        tgl_mulai=tgl_mulai,
        tgl_akhir=tgl_akhir,
        no_rm=no_rm,
        status=status,
        max_force_days=max_days,
    )
    return templates.TemplateResponse(request, "kasir_cari_transaksi.html", ctx)



