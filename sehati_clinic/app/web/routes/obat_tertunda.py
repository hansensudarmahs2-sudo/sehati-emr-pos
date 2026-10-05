"""
Web routes — Obat Tertunda (P1-1). Ref OBAT_TERTUNDA_DESIGN.md.

- GET  /web/obat-tertunda                      - worklist obat dibayar tapi belum diserah
- POST /web/obat-tertunda/{id}/serahkan        - serah sekarang (potong stok, keluar daftar)
- POST /web/obat-tertunda/{id}/ubah-tgl        - reschedule tgl_janji_kirim

Role: FO / Kasir / Apotek / Owner / Superadmin / Admin (saling mengingatkan).
"""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.schemas.apotek import SerahkanObatRequest
from app.services.apotek_service import ApotekService
from app.web.routes._shared import (
    build_shell_context,
    forbidden,
    get_user_from_cookie,
    login_redirect,
    require_antrian_mgmt_role,
    require_apoteker_role,
    require_kasir_role,
    templates,
)

router = APIRouter(tags=["Web Obat Tertunda"])


def _can(user) -> bool:
    return (
        require_antrian_mgmt_role(user)
        or require_kasir_role(user)
        or require_apoteker_role(user)
    )


@router.get("/obat-tertunda", response_class=HTMLResponse)
def obat_tertunda_list(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Halaman Obat Tertunda hanya untuk FO / Kasir / Apotek / Owner.")
    items = ApotekService(db).list_obat_tertunda()
    today = date.today()

    # T32: refund atas transaksi HARI LAMPAU butuh PIN Admin/Superadmin/Owner, dan
    # penyetuju ≠ pemroses. Penanda di sini hanya untuk MENAMPILKAN kotak PIN — yang
    # memutuskan tetap server (`KasirService._otorisasi_refund_lampau`); kalau penanda
    # ini meleset, server menolak dengan pesan yang meminta PIN.
    from sqlalchemy import func, select
    from app.db.models import MasterStaf, TransaksiKasir
    from app.services.kasir_service import _ROLES_PENYETUJU_REFUND
    _ids = [i["id_kunjungan"] for i in items]
    _tgl_bayar = dict(db.execute(
        select(TransaksiKasir.id_kunjungan, func.max(TransaksiKasir.waktu_bayar))
        .where(TransaksiKasir.id_kunjungan.in_(_ids))
        .where(TransaksiKasir.status_transaksi == "BAYAR")
        .group_by(TransaksiKasir.id_kunjungan)
    ).all()) if _ids else {}
    for i in items:
        _wb = _tgl_bayar.get(i["id_kunjungan"])
        i["butuh_otorisasi"] = _wb is not None and _wb.date() < today
    penyetuju = [
        s for s in db.execute(
            select(MasterStaf).where(MasterStaf.is_active.is_(True))
            .where(MasterStaf.pin.is_not(None)).where(MasterStaf.pin != "")
            .order_by(MasterStaf.nama_staf)
        ).scalars().all()
        if (s.role.value if hasattr(s.role, "value") else str(s.role)) in _ROLES_PENYETUJU_REFUND
        and s.id_staf != user.id_staf
    ]

    ctx = build_shell_context(
        user, db=db, current_path="/web/obat-tertunda", page_subtitle="Obat Tertunda",
        items=items, today=today, penyetuju_refund=penyetuju,
        # Pembatalan berikut pengembalian uang hanya untuk peran kasir (lihat route
        # batalkan-item): apoteker tahu obatnya tak datang, kasir yang mengeluarkan uang.
        can_batalkan_item=require_kasir_role(user),  # lihat route batalkan-item
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "obat_tertunda_list.html", ctx)


@router.post("/obat-tertunda/{id_kunjungan}/serahkan", response_class=HTMLResponse)
def obat_tertunda_serahkan(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    try:
        ApotekService(db).serahkan_obat(
            payload=SerahkanObatRequest(id_kunjungan=id_kunjungan),
            id_staf_apoteker=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(str(e.detail))}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(f'Gagal: {e!s}')}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/web/obat-tertunda?ok={quote('Obat diserahkan & stok terpotong.')}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/obat-tertunda/{id_kunjungan}/batalkan-item", response_class=HTMLResponse)
async def obat_tertunda_batalkan_item(id_kunjungan: int, request: Request, db: DbSession):
    """Task #54-F: batalkan SATU item obat tertunda + kembalikan uangnya.

    Sengaja dipagari ke peran KASIR (termasuk Admin/Owner/Superadmin), bukan `_can`
    yang juga mencakup Apoteker & FO: apoteker yang tahu obatnya tidak datang, tapi
    yang mengeluarkan uang dari laci adalah kasir — dan itu yang harus bertanggung
    jawab atas angkanya saat tutup kasir.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_kasir_role(user):
        return forbidden("Pembatalan dengan pengembalian uang hanya untuk Kasir / Owner.")

    f = await request.form()
    jenis = (f.get("jenis") or "").strip().upper()
    raw_id = (f.get("id_item") or "").strip()
    alasan = (f.get("alasan") or "").strip()
    metode = (f.get("metode_refund") or "TUNAI").strip().upper()
    # T32: hanya terisi untuk transaksi hari lampau. PIN TIDAK PERNAH dimasukkan ke
    # URL atau pesan redirect — hanya diteruskan ke service untuk diverifikasi.
    pin_otorisasi = (f.get("pin_otorisasi") or "").strip() or None
    try:
        id_staf_otorisasi = int(f.get("id_staf_otorisasi") or 0) or None
    except (TypeError, ValueError):
        id_staf_otorisasi = None
    try:
        id_item = int(raw_id)
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/web/obat-tertunda?err={quote('Item tidak dikenali.')}",
            status_code=status.HTTP_303_SEE_OTHER)
    if jenis not in ("RESEP", "RACIKAN"):
        return RedirectResponse(
            url=f"/web/obat-tertunda?err={quote('Jenis item tidak dikenali.')}",
            status_code=status.HTTP_303_SEE_OTHER)

    from app.services.kasir_service import KasirService
    try:
        hasil = KasirService(db).refund_item_tertunda(
            id_resep=id_item if jenis == "RESEP" else None,
            id_kunjungan_racikan=id_item if jenis == "RACIKAN" else None,
            alasan=alasan, metode_refund=metode,
            actor_id_staf=user.id_staf,
            id_staf_otorisasi=id_staf_otorisasi, pin_otorisasi=pin_otorisasi,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)
    msg = hasil.get("message", "Item dibatalkan & uang dikembalikan.")
    return RedirectResponse(url=f"/web/obat-tertunda?ok={quote(msg)}",
                            status_code=status.HTTP_303_SEE_OTHER)


@router.post("/obat-tertunda/{id_kunjungan}/ubah-tgl", response_class=HTMLResponse)
async def obat_tertunda_ubah_tgl(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not _can(user):
        return forbidden("Tidak berhak.")
    f = await request.form()
    raw = (f.get("tgl_baru") or "").strip()
    tgl = None
    if raw:
        try:
            tgl = date.fromisoformat(raw)
        except ValueError:
            tgl = None
    if tgl is None:
        return RedirectResponse(url=f"/web/obat-tertunda?err={quote('Tanggal baru tidak valid.')}", status_code=status.HTTP_303_SEE_OTHER)
    from app.db.models.kunjungan import Kunjungan
    kj = db.get(Kunjungan, id_kunjungan)
    if kj is not None and kj.tgl_janji_kirim is not None:
        kj.tgl_janji_kirim = tgl
        db.commit()
    return RedirectResponse(url=f"/web/obat-tertunda?ok={quote('Tanggal kirim diperbarui.')}", status_code=status.HTTP_303_SEE_OTHER)
