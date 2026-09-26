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
# PENEBUSAN RESEP (2026-09-25) — tiga asal: RESEP_LUAR / RESEP_ONLINE / TEBUS_LANJUT
# Desain: Project_Memory/DESAIN_RESEP_LUAR_APOTEK.md
#
# Apoteker TIDAK diberi akses modul pasien maupun kasir. Pencarian & pendaftaran
# ringkas pasien disediakan DI SINI dalam bentuk sesempit mungkin: hanya mencari dan
# membuat, tidak bisa mengubah data pasien dan tidak bisa membuka rekam medis.
# =============================================================================
def _daftar_dokter(db):
    """Staf berperan DOKTER — untuk resep konsultasi online."""
    from sqlalchemy import select
    from app.db.models import MasterStaf, StafRoleEnum
    return list(db.execute(
        select(MasterStaf)
        .where(MasterStaf.role == StafRoleEnum.DOKTER, MasterStaf.is_active.is_(True))
        .order_by(MasterStaf.nama_staf.asc())
    ).scalars().all())


@router.get("/apotek/tebus-resep", response_class=HTMLResponse)
def apotek_tebus_resep(request: Request, db: DbSession, q: str = "", id_pasien: str = ""):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from app.services.pasien_service import PasienService

    svc_pasien = PasienService(db)
    hasil_cari, pasien, resep_lama = [], None, []
    _id = None
    try:
        _id = int(id_pasien) if id_pasien else None
    except ValueError:
        _id = None

    if _id:
        from app.db.models import Pasien
        pasien = db.get(Pasien, _id)
        if pasien is not None and not pasien.is_active:
            pasien = None  # pasien nonaktif tidak boleh dipakai transaksi baru
        if pasien is not None:
            resep_lama = ApotekService(db).list_resep_belum_ditebus(_id)
    elif q.strip():
        hasil_cari = svc_pasien.search(keyword=q.strip(), limit=20)

    ctx = build_shell_context(
        user, db=db, current_path="/web/apotek/tebus-resep",
        page_subtitle="Tebus Resep",
        q=q, hasil_cari=hasil_cari, pasien=pasien, resep_lama=resep_lama,
        daftar_dokter=_daftar_dokter(db),
        master_produks=MasterProdukService(db).list_all(only_active=True, limit=500),
        max_umur=ApotekService.MAX_UMUR_RESEP_HARI,
        ok=request.query_params.get("ok"), err=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "apotek_tebus_resep.html", ctx)


@router.post("/apotek/tebus-resep/pasien-baru", response_class=HTMLResponse)
async def apotek_tebus_pasien_baru(request: Request, db: DbSession):
    """Pendaftaran RINGKAS oleh apoteker — hanya membuat, tidak membuat kunjungan."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from datetime import date as _date
    from app.schemas.pasien import PasienBaruRequest
    from app.services.pasien_service import DuplikatPasienError, PasienService

    f = await request.form()
    _tgl = (f.get("tgl_lahir") or "").strip()
    try:
        payload = PasienBaruRequest(
            nama=(f.get("nama") or "").strip(),
            jenis_kelamin=(f.get("jenis_kelamin") or "L").strip(),
            nomor_telepon=(f.get("nomor_telepon") or "").strip(),
            tgl_lahir=_date.fromisoformat(_tgl) if _tgl else None,
        )
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(
            url=f"/web/apotek/tebus-resep?err={quote(f'Data pasien tidak lengkap: {e}')}",
            status_code=status.HTTP_303_SEE_OTHER)

    try:
        hasil = PasienService(db).register_pasien_baru(
            payload=payload, id_staf_fo=user.id_staf, request=request,
            buat_kunjungan=False,
            konfirmasi_duplikat=(f.get("konfirmasi_duplikat") == "1"),
        )
    except DuplikatPasienError as e:
        # Jangan diam-diam membuat pasien kembar dari meja apotek — arahkan mencari dulu.
        _nama = (f.get("nama") or "").strip()
        _pesan = ("Pasien serupa sudah ada — pilih dari hasil pencarian, "
                  "atau daftarkan ulang dengan mencentang konfirmasi.")
        return RedirectResponse(
            url=f"/web/apotek/tebus-resep?q={quote(_nama)}&err={quote(_pesan)}",
            status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/apotek/tebus-resep?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER)

    _idp = (hasil.get("data") or {}).get("id_pasien") if isinstance(hasil, dict) else None
    return RedirectResponse(
        url=f"/web/apotek/tebus-resep?id_pasien={_idp}&ok={quote('Pasien terdaftar.')}",
        status_code=status.HTTP_303_SEE_OTHER)


@router.post("/apotek/tebus-resep/simpan", response_class=HTMLResponse)
async def apotek_tebus_resep_simpan(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_apoteker_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    from app.services.kunjungan_service import KunjunganService

    f = await request.form()
    try:
        id_pasien = int((f.get("id_pasien") or "").strip())
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/web/apotek/tebus-resep?err={quote('Pasien belum dipilih.')}",
            status_code=status.HTTP_303_SEE_OTHER)

    jenis = (f.get("jenis") or "").strip().upper()
    _kembali = f"/web/apotek/tebus-resep?id_pasien={id_pasien}"

    produk_list, id_kunjungan_asal = [], None
    if jenis == "TEBUS_LANJUT":
        # Yang dicentang adalah baris resep LAMA; kita salin qty & aturan pakainya apa
        # adanya, dan menautkan salinan ke asalnya (penanda anti tebus ganda).
        from app.db.models import KunjunganResep
        for raw in f.getlist("id_resep_asal"):
            try:
                _rid = int(str(raw).strip())
            except (TypeError, ValueError):
                continue
            asal = db.get(KunjunganResep, _rid)
            if asal is None:
                continue
            produk_list.append({
                "id_produk": asal.id_produk, "qty": float(asal.qty or 0),
                "aturan_pakai": asal.aturan_pakai or "", "id_resep_asal": _rid,
            })
            id_kunjungan_asal = id_kunjungan_asal or asal.id_kunjungan
        if not produk_list:
            return RedirectResponse(
                url=f"{_kembali}&err={quote('Belum ada resep lama yang dicentang.')}",
                status_code=status.HTTP_303_SEE_OTHER)
    else:
        ids = f.getlist("id_produk")
        qtys = f.getlist("qty")
        aturans = f.getlist("aturan_pakai")
        for i, raw in enumerate(ids):
            if not str(raw).strip():
                continue
            try:
                produk_list.append({
                    "id_produk": int(raw),
                    "qty": float(qtys[i]) if i < len(qtys) and qtys[i] else 1.0,
                    "aturan_pakai": aturans[i] if i < len(aturans) else "",
                })
            except (TypeError, ValueError):
                continue

    _iddok = (f.get("id_dokter") or "").strip()
    try:
        hasil = KunjunganService(db).beli_produk_lengkap(
            id_pasien=id_pasien,
            produk_list=produk_list,
            id_staf_fo=user.id_staf,
            keluhan_utama=(f.get("keterangan") or "").strip(),
            request=request,
            jenis_kunjungan=jenis,
            peresep_nama=f.get("peresep_nama"),
            peresep_asal=f.get("peresep_asal"),
            id_dokter=int(_iddok) if _iddok else None,
            id_kunjungan_asal=id_kunjungan_asal,
        )
    except HTTPException as e:
        return RedirectResponse(url=f"{_kembali}&err={quote(str(e.detail))}",
                                status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(url=f"{_kembali}&err={quote(f'Gagal: {e!s}')}",
                                status_code=status.HTTP_303_SEE_OTHER)

    _data = hasil.get("data") if isinstance(hasil, dict) else {}
    _no = (_data or {}).get("nomor_antrean")

    # Draf SOAP dari percakapan online — disimpan sebagai baris `pemeriksaan_klinis`
    # dengan dokter masih KOSONG dan status DRAFT_APOTEK. Dokter yang dituju akan
    # membacanya, menyunting bila perlu, lalu menjadikannya SOAP miliknya.
    _draf = (f.get("draf_soap") or "").strip()
    if jenis == "RESEP_ONLINE" and _draf and _data:
        from datetime import datetime as _dt
        from app.db.models import PemeriksaanKlinis
        _raw_wk = (f.get("waktu_konsultasi") or "").strip()
        try:
            _wk = _dt.fromisoformat(_raw_wk) if _raw_wk else _dt.now()
        except ValueError:
            _wk = _dt.now()
        db.add(PemeriksaanKlinis(
            id_kunjungan=_data["id_kunjungan"],
            id_pasien=id_pasien,
            id_staf_dokter=None,              # belum ada yang bertanggung jawab
            anamnesa=_draf,
            status_soap="DRAFT_APOTEK",
            id_staf_penyusun=user.id_staf,
            waktu_konsultasi=_wk,             # KAPAN percakapannya, bukan kapan dicatat
        ))
        db.commit()
    return RedirectResponse(
        url=f"/web/apotek/tebus-resep?ok="
            f"{quote(f'Tersimpan. Antrian bayar no. {_no} — arahkan pasien ke kasir.')}",
        status_code=status.HTTP_303_SEE_OTHER)


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
