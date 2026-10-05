"""
Web routes — Retur dari pasien (obat/produk yang SUDAH diserahkan).
Rancangan: Project_Memory/DESAIN_RETUR_DARI_PASIEN.md. Logika di `ReturPasienService`.

- GET  /web/kasir/retur/{id_transaksi}        — daftar item yang bisa diretur
- POST /web/kasir/retur/{id_transaksi}        — buat satu retur (satu item)
- GET  /web/kasir/retur/nota/{id_retur}       — nota retur (cetak)

Peran: KASIR_ROLES (Kasir/Admin/Owner/Superadmin) — yang mengeluarkan uang dari laci
yang bertanggung jawab atas angkanya (pola sama dengan refund obat tertunda).
⚠ PIN tidak pernah dimasukkan ke URL atau pesan redirect.
"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.services.kasir_service import daftar_penyetuju_refund
from app.services.klinik_config_service import KlinikConfigService
from app.services.retur_pasien_service import ReturPasienService
from app.web.routes._shared import (
    build_shell_context, forbidden, get_user_from_cookie, login_redirect,
    require_kasir_role, templates,
)

router = APIRouter(tags=["Web Retur Pasien"])

ALASAN = [
    ("TIDAK_PUAS", "Tidak puas"), ("ALERGI", "Dugaan alergi"),
    ("EFEK_SAMPING", "Efek samping"), ("SALAH_PRODUK", "Salah produk"),
    ("RUSAK", "Produk rusak"), ("LAINNYA", "Lainnya"),
]


@router.get("/kasir/retur/{id_transaksi}", response_class=HTMLResponse)
def retur_halaman(id_transaksi: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_kasir_role(user):
        return forbidden("Retur dari pasien hanya untuk Kasir / Admin / Owner.")
    try:
        data = ReturPasienService(db).daftar_item_retur(id_transaksi)
    except HTTPException as e:
        return RedirectResponse(url=f"/web/kasir/cari-transaksi?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    ctx = build_shell_context(
        user, db=db, current_path="/web/kasir/cari-transaksi",
        page_subtitle=f"Retur dari pasien — transaksi #{id_transaksi}",
        **data, alasan_list=ALASAN,
        penyetuju=daftar_penyetuju_refund(db, kecuali_id_staf=user.id_staf),
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "kasir_retur_pasien.html", ctx)


@router.post("/kasir/retur/{id_transaksi}", response_class=HTMLResponse)
async def retur_simpan(id_transaksi: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_kasir_role(user):
        return forbidden("Retur dari pasien hanya untuk Kasir / Admin / Owner.")
    kembali = f"/web/kasir/retur/{id_transaksi}"
    f = await request.form()

    def _int(nama):
        try:
            return int(f.get(nama) or 0) or None
        except (TypeError, ValueError):
            return None

    jenis_item = (f.get("jenis_item") or "").upper()
    id_item = _int("id_item")
    jenis = (f.get("jenis") or "REFUND").upper()
    pengganti = []
    if jenis == "TUKAR" and _int("pengganti_id_produk"):
        pengganti = [{"id_produk": _int("pengganti_id_produk"),
                      "qty": (f.get("pengganti_qty") or "1").strip()}]
    try:
        hasil = ReturPasienService(db).buat_retur(
            id_resep=id_item if jenis_item == "RESEP" else None,
            id_kunjungan_racikan=id_item if jenis_item == "RACIKAN" else None,
            qty=(f.get("qty") or "").strip() or None,
            jenis=jenis, alasan_kode=(f.get("alasan_kode") or "").upper(),
            alasan_teks=(f.get("alasan_teks") or "").strip(),
            stok_kembali=(f.get("stok_kembali") == "1"),
            metode_refund=(f.get("metode") or "TUNAI").upper(),
            pengganti=pengganti,
            id_staf_otorisasi=_int("id_staf_otorisasi"),
            pin_otorisasi=(f.get("pin_otorisasi") or "").strip() or None,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"{kembali}?err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/web/kasir/retur/nota/{hasil['id_retur']}?ok={quote(hasil['message'])}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.get("/kasir/retur/nota/{id_retur}", response_class=HTMLResponse)
def retur_nota(id_retur: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return login_redirect()
    if not require_kasir_role(user):
        return forbidden("Nota retur hanya untuk Kasir / Admin / Owner.")
    try:
        ctx = ReturPasienService(db).konteks_nota_retur(id_retur)
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.detail}</div>", status_code=e.status_code)
    from datetime import datetime
    ctx.update({
        "klinik": KlinikConfigService(db).get_config(),
        "ok": request.query_params.get("ok"),
        "tgl_cetak": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return templates.TemplateResponse(request, "print/nota_retur.html", ctx)


__all__ = ["router"]
