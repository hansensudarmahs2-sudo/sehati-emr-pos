"""
Pasien web routes (search + detail + riwayat):
- GET /web/pasien                        — search page
- GET /web/pasien/cari                   — HTMX partial (table rows)
- GET /web/pasien/{id_pasien}            — detail pasien
- GET /web/pasien/{id_pasien}/riwayat    — riwayat lengkap

Catatan: route /pasien/cari harus didefinisikan SEBELUM /pasien/{id_pasien}
supaya FastAPI tidak salah match "cari" sebagai id_pasien.
"""

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.repositories.pemeriksaan_repo import PemeriksaanRepository
from app.schemas.kunjungan import KunjunganLamaRequest
from app.services.antropometri_service import AntropometriService
from app.schemas.antropometri import AntropometriUpsertRequest
from app.services.kunjungan_service import KunjunganService
from app.services.pasien_service import PasienService
from app.services.penyakit_kronis_service import PenyakitKronisService
from app.services.antro_report_service import AntroReportService
from app.services.master_membership_service import MasterMembershipService
from app.services.membership_service import MembershipService
from app.schemas.pasien import AlergiAddRequest, AlergiUpdateRequest, PenyakitKronisAddRequest, PenyakitKronisUpdateRequest, PasienUpdateRequest
from app.db.models import TingkatKeparahanAlergiEnum, GenderEnum, MembershipTierEnum
from app.services.series_service import SeriesService
from app.web.routes._shared import (
    build_shell_context,
    get_dokter_aktif_list,
    get_user_from_cookie,
    require_antrian_mgmt_role,
    require_kasir_role,
    templates,
)


router = APIRouter(tags=["Web Pasien"])


# =============================================================================
# GET /web/pasien — search page
# =============================================================================
@router.get("/pasien", response_class=HTMLResponse)
def pasien_search_page(request: Request, db: DbSession):
    """Render halaman cari pasien (search + result placeholder)."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/pasien",
        page_subtitle="Cari berdasarkan nama, no_rm, telepon, atau alamat",
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
        # FO-ASSIGN-DOKTER #329: dokter list untuk dropdown +Antrian
        dokter_list=get_dokter_aktif_list(db),
    )
    return templates.TemplateResponse(request, "pasien_search.html", ctx)


# =============================================================================
# GET /web/pasien/cari — HTMX partial (table rows)
# =============================================================================
@router.get("/pasien/cari", response_class=HTMLResponse)
def pasien_search_partial(
    request: Request,
    db: DbSession,
    keyword: str = "",
):
    """HTMX endpoint — return _pasien_rows.html partial saja."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse(
            "<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>"
            "Sesi habis, silakan login ulang.</div>",
            status_code=401,
        )

    keyword = (keyword or "").strip()
    hasil = []
    if keyword:
        try:
            rows = PasienService(db).search(keyword=keyword, limit=50)
            series_svc = SeriesService(db)
            hasil = []
            for p in rows:
                # Fetch series aktif (rencana PENDING) per pasien
                series_aktif_raw = []
                try:
                    series_aktif_raw = series_svc.list_active_for_pasien(p.id_pasien)
                except Exception:
                    series_aktif_raw = []
                # Flatten ke list rencana PENDING (untuk button "Lanjut Series #N")
                series_pending_flat = []
                for g in series_aktif_raw:
                    for r in g.get("rencana_pending", []):
                        series_pending_flat.append({
                            "id_rencana": r["id_rencana"],
                            "urutan_sesi": r["urutan_sesi"],
                            "nama_tindakan": g["nama_tindakan"],
                            "total_sesi": g["total_sesi"],
                        })
                hasil.append({
                    "id_pasien": p.id_pasien,
                    "no_rm": p.no_rm,
                    "nama": p.nama,
                    "jenis_kelamin": (
                        p.jenis_kelamin.value
                        if hasattr(p.jenis_kelamin, "value")
                        else (str(p.jenis_kelamin) if p.jenis_kelamin else None)
                    ),
                    "nomor_telepon": p.nomor_telepon,
                    "tipe_membership": (
                        p.tipe_membership.value
                        if hasattr(p.tipe_membership, "value")
                        else (str(p.tipe_membership) if p.tipe_membership else None)
                    ),
                    "series_pending": series_pending_flat,
                })
        except Exception as e:
            return HTMLResponse(
                f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>"
                f"Error: {e!s}</div>",
                status_code=500,
            )

    return templates.TemplateResponse(
        request,
        "_pasien_rows.html",
        {
            "hasil": hasil,
            "keyword": keyword,
            "can_add_antrian": require_antrian_mgmt_role(user),
            "flash": request.query_params.get("ok"),
            "flash_error": request.query_params.get("err"),
            # FO-ASSIGN-DOKTER #329
            "dokter_list": get_dokter_aktif_list(db),
        },
    )
# =============================================================================
# GET /web/pasien/_produk-row - HTMX partial: 1 row produk untuk Beli Produk form
# =============================================================================
@router.get("/pasien/_produk-row", response_class=HTMLResponse)
def pasien_produk_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    from app.services.master_produk_service import MasterProdukService
    produks = MasterProdukService(db).list_all(only_active=True, limit=500)
    return templates.TemplateResponse(request, "_produk_pembelian_row.html", {"master_produks": produks})




# =============================================================================
# GET /web/pasien/{id} — detail pasien
# =============================================================================
@router.get("/pasien/{id_pasien}", response_class=HTMLResponse)
def pasien_detail_page(
    id_pasien: int,
    request: Request,
    db: DbSession,
):
    """Render halaman detail pasien (info + alergi + penyakit + antropometri)."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        detail = PasienService(db).get_detail(id_pasien)
    except HTTPException as e:
        return HTMLResponse(
            f"""<div class="p-8 text-center">
                <h2 class="text-xl font-bold text-slate-800">Pasien tidak ditemukan</h2>
                <p class="text-slate-500 mt-2">{e.detail}</p>
                <a href="/web/pasien" class="inline-block mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg">Kembali</a>
            </div>""",
            status_code=e.status_code,
        )

    # V7.2.1 audit akses-baca: catat siapa membuka rekam medis pasien ini
    from app.services.audit_service import AuditService as _AS
    _AS(db).log_view(user.id_staf, id_pasien, keterangan="Buka detail pasien", request=request)

    pasien_dict = detail.model_dump()
    # Format enum values
    if pasien_dict.get("jenis_kelamin"):
        pasien_dict["jenis_kelamin"] = (
            pasien_dict["jenis_kelamin"].value
            if hasattr(pasien_dict["jenis_kelamin"], "value")
            else str(pasien_dict["jenis_kelamin"])
        )
    if pasien_dict.get("tipe_membership"):
        pasien_dict["tipe_membership"] = (
            pasien_dict["tipe_membership"].value
            if hasattr(pasien_dict["tipe_membership"], "value")
            else str(pasien_dict["tipe_membership"])
        )
    for a in pasien_dict.get("alergi", []):
        if a.get("tingkat_keparahan"):
            a["tingkat_keparahan"] = (
                a["tingkat_keparahan"].value
                if hasattr(a["tingkat_keparahan"], "value")
                else str(a["tingkat_keparahan"])
            )

    # Antropometri terakhir + clinical (BMI/fat%/lean%)
    try:
        antro_resp = AntropometriService(db).get_terakhir_with_clinical(id_pasien)
        antropometri = antro_resp.model_dump()
    except (HTTPException, Exception):
        antropometri = {"has_data": False}

    # Riwayat SOAP - 5 terakhir
    soap_riwayat = []
    try:
        rows = PemeriksaanRepository(db).get_riwayat_soap(id_pasien, limit=5)
        for soap, dokter in rows:
            soap_riwayat.append({
                "id_pemeriksaan": soap.id_pemeriksaan,
                "tanggal": soap.created_at.strftime("%Y-%m-%d %H:%M") if soap.created_at else None,
                "nama_dokter": dokter.nama_staf if dokter else None,
                "anamnesa": soap.anamnesa,
                "pemeriksaan_fisik": soap.pemeriksaan_fisik,
                "diagnosa": soap.diagnosa,
                "saran_treatment": soap.saran_treatment,
                "saran_produk": soap.saran_produk,
            })
    except Exception:
        soap_riwayat = []

    # Series treatment aktif (rencana PENDING) + kunjungan aktif hari ini
    series_aktif = []
    kunjungan_aktif_id = None
    try:
        from app.services.series_service import SeriesService
        series_aktif = SeriesService(db).list_active_for_pasien(id_pasien)
        # Cari kunjungan pasien hari ini yang status_antrian masih aktif
        # (bukan COMPLETED/BATAL) → untuk button "Pakai sesi" link ke kunjungan ini
        from datetime import date as _date
        from sqlalchemy import select as _sel, func as _func
        from app.db.models import Kunjungan as _K
        today = _date.today()
        kunj_row = db.execute(
            _sel(_K.id_kunjungan, _K.status_antrian)
            .where(_K.id_pasien == id_pasien)
            .where(_func.date(_K.tgl_kunjungan) == today)
            .where(_K.status_antrian.notin_(("COMPLETED", "BATAL")))
            .order_by(_K.id_kunjungan.desc())
            .limit(1)
        ).first()
        if kunj_row:
            kunjungan_aktif_id = int(kunj_row[0])
    except Exception as exc:  # noqa: BLE001 — graceful degradation
        # Series fetch gagal — render tetap, tanpa series section
        import logging
        logging.getLogger("app.pasien").warning(
            "Series fetch failed for pasien %s: %s", id_pasien, exc,
        )

    # #362C - Read tier aktif untuk edit dropdown
    try:
        tiers_active = MasterMembershipService(db).list_all(only_active=True, limit=100)
        available_tiers = [
            {"nama_tier": t.nama_tier, "harga_aktivasi": float(t.harga_aktivasi or 0)}
            for t in tiers_active
        ]
    except Exception:
        available_tiers = []

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/pasien",
        pasien=pasien_dict,
        antropometri=antropometri,
        antro_laporan=AntroReportService().laporan_by_rm(pasien_dict.get("no_rm")),
        soap_riwayat=soap_riwayat,
        series_aktif=series_aktif,
        kunjungan_aktif_id=kunjungan_aktif_id,
        available_tiers=available_tiers,
        master_penyakit_list=PenyakitKronisService(db).list_master(),
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pasien_detail.html", ctx)


# =============================================================================
# POST /web/series/use — FO pakai sesi rencana berikutnya
# =============================================================================
@router.post("/series/use", response_class=HTMLResponse)
async def series_use_session(request: Request, db: DbSession):
    """FO klik tombol 'Pakai Sesi' di pasien detail → link rencana ke kunjungan aktif."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    form_data = await request.form()
    from urllib.parse import quote

    try:
        id_rencana = int(form_data.get("id_rencana") or 0)
        id_kunjungan = int(form_data.get("id_kunjungan") or 0)
        id_pasien_form = int(form_data.get("id_pasien") or 0)
    except Exception:
        return RedirectResponse(url="/web/pasien", status_code=status.HTTP_303_SEE_OTHER)

    if not (id_rencana and id_kunjungan and id_pasien_form):
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien_form}?err={quote('Data form tidak lengkap.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        from app.services.series_service import SeriesService
        result = SeriesService(db).use_session(
            id_rencana=id_rencana,
            id_kunjungan=id_kunjungan,
            actor_id_staf=user.id_staf,
            request=request,
        )
        msg = result.get("message", "Sesi berhasil di-booked.")
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien_form}?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien_form}?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/web/pasien/{id_pasien_form}?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/pasien/{id}/riwayat — riwayat lengkap


# =============================================================================
@router.get("/pasien/{id_pasien}/riwayat", response_class=HTMLResponse)
def pasien_riwayat_page(
    id_pasien: int,
    request: Request,
    db: DbSession,
):
    """Render halaman riwayat pasien — kunjungan + treatment + produk."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        riwayat_resp = PasienService(db).get_riwayat(id_pasien=id_pasien)
    except HTTPException as e:
        return HTMLResponse(
            f"<div class='p-8 text-center'>"
            f"<h2 class='text-xl font-bold text-slate-800'>Pasien tidak ditemukan</h2>"
            f"<p class='text-slate-500 mt-2'>{e.detail}</p>"
            f"<a href='/web/pasien' class='inline-block mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg'>Kembali</a>"
            f"</div>",
            status_code=e.status_code,
        )

    from app.services.audit_service import AuditService as _AS
    _AS(db).log_view(user.id_staf, id_pasien, keterangan="Buka riwayat pasien", request=request)

    riwayat_dict = riwayat_resp.model_dump()
    info = riwayat_dict.get("info_pasien", {})
    if info.get("jenis_kelamin") and hasattr(info["jenis_kelamin"], "value"):
        info["jenis_kelamin"] = info["jenis_kelamin"].value

    # Riwayat SOAP dengan nama dokter — same pattern as pasien_detail
    soap_riwayat = []
    try:
        rows = PemeriksaanRepository(db).get_riwayat_soap(id_pasien, limit=10)
        for soap, dokter in rows:
            soap_riwayat.append({
                "id_pemeriksaan": soap.id_pemeriksaan,
                "id_kunjungan": soap.id_kunjungan,
                "tanggal": soap.created_at.strftime("%Y-%m-%d %H:%M") if soap.created_at else None,
                "nama_dokter": dokter.nama_staf if dokter else None,
                "anamnesa": soap.anamnesa,
                "pemeriksaan_fisik": soap.pemeriksaan_fisik,
                "diagnosa": soap.diagnosa,
            })
    except Exception:
        soap_riwayat = []

    # Build kunjungan_to_dokter map — inject ke kunjungan items supaya display dokter
    kunjungan_to_dokter = {}
    for s in soap_riwayat:
        if s.get("id_kunjungan") and s.get("nama_dokter"):
            kunjungan_to_dokter.setdefault(s["id_kunjungan"], s["nama_dokter"])
    for k in riwayat_dict.get("kunjungan", []):
        k["nama_dokter"] = kunjungan_to_dokter.get(k.get("id_kunjungan"))

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/pasien",
        riwayat=riwayat_dict,
        soap_riwayat=soap_riwayat,
    )
    return templates.TemplateResponse(request, "pasien_riwayat.html", ctx)


# =============================================================================
# POST /web/pasien/{id_pasien}/buat-antrian
# Tambah pasien existing ke antrian hari ini (Patch 2).
# Role gate: FO/Admin/Owner/Superadmin.
# =============================================================================
@router.post("/pasien/{id_pasien}/buat-antrian")
def pasien_buat_antrian(
    id_pasien: int,
    request: Request,
    db: DbSession,
    status_antrian: str = Form(...),
    keyword: str = Form(""),
    keluhan_utama: str = Form(""),
    id_staf_dokter_assigned: str = Form(""),  # FO-ASSIGN-DOKTER #329
):
    """Daftar pasien existing ke kunjungan baru, redirect ke search dengan flash."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    ALLOWED = {"ANTRI_KONSULTASI", "ANTRI_TREATMENT", "ANTRI_BAYAR"}
    if status_antrian not in ALLOWED:
        return RedirectResponse(
            url=f"/web/pasien?err=Status+tidak+valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # FO-ASSIGN-DOKTER (Task #329): parse optional dokter assignment
    id_dokter_int = None
    if id_staf_dokter_assigned and id_staf_dokter_assigned.strip():
        try:
            id_dokter_int = int(id_staf_dokter_assigned.strip())
            if id_dokter_int < 1:
                id_dokter_int = None
        except ValueError:
            id_dokter_int = None

    try:
        payload = KunjunganLamaRequest(
            id_pasien=id_pasien,
            status_antrian=status_antrian,
            keluhan_utama=(keluhan_utama or "").strip(),
            sumber_pendaftaran="WALK_IN",
            antropometri=None,
            id_staf_dokter_assigned=id_dokter_int,
        )
        result = KunjunganService(db).kunjungan_lama(
            payload=payload,
            id_staf_fo=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/pasien?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/web/pasien?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    data = result.get("data", {}) if isinstance(result, dict) else {}
    nomor_antrean = data.get("nomor_antrean", "?")
    label_map = {
        "ANTRI_KONSULTASI": "Antri Konsultasi",
        "ANTRI_TREATMENT": "Antri Tindakan",
        "ANTRI_BAYAR": "Antri Bayar",
    }
    label = label_map.get(status_antrian, status_antrian)
    msg = f"Pasien masuk antrian {label}, nomor #{nomor_antrean}."
    from urllib.parse import quote
    _idk = data.get("id_kunjungan")
    _pp = f"&print_antrian={_idk}" if _idk else ""
    return RedirectResponse(
        url=f"/web/pasien?ok={quote(msg)}{_pp}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# POST /web/pasien/{id_pasien}/buat-antrian-series
# FIX-ST-3 — FO booking lanjutan series treatment:
#   1) Buat kunjungan baru langsung ke ANTRI_TREATMENT
#   2) Convert rencana PENDING → SCHEDULED + buat KunjunganTindakan
#   3) Redirect ke search dengan flash success
# Role gate: FO/Admin/Owner/Superadmin.
# =============================================================================
@router.post("/pasien/{id_pasien}/buat-antrian-series")
def pasien_buat_antrian_series(
    id_pasien: int,
    request: Request,
    db: DbSession,
    id_rencana: int = Form(...),
    keyword: str = Form(""),
):
    """Daftar pasien existing ke kunjungan baru + pakai sesi series langsung."""
    from urllib.parse import quote

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    # Validasi rencana exists + pasien match + status PENDING (cheap guard sebelum buat kunjungan)
    try:
        from app.db.models import PasienRencanaTreatment
        rencana = db.get(PasienRencanaTreatment, id_rencana)
        if rencana is None:
            return RedirectResponse(
                url=f"/web/pasien?err={quote('Rencana series tidak ditemukan.')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if rencana.id_pasien != id_pasien:
            return RedirectResponse(
                url=f"/web/pasien?err={quote('Rencana series milik pasien lain.')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        status_v = (
            rencana.status.value
            if hasattr(rencana.status, "value")
            else str(rencana.status)
        )
        if status_v != "PENDING":
            return RedirectResponse(
                url=f"/web/pasien?err={quote(f'Sesi {rencana.urutan_sesi} sudah berstatus {status_v}.')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        nama_tindakan = rencana.nama_tindakan or "treatment"
        urutan_sesi = rencana.urutan_sesi
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien?err={quote(f'Gagal validasi rencana: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Step 1: Buat kunjungan baru ke ANTRI_TREATMENT
    try:
        payload = KunjunganLamaRequest(
            id_pasien=id_pasien,
            status_antrian="ANTRI_TREATMENT",
            keluhan_utama=f"Lanjut series {nama_tindakan} sesi {urutan_sesi}",
            sumber_pendaftaran="WALK_IN",
            antropometri=None,
        )
        result = KunjunganService(db).kunjungan_lama(
            payload=payload,
            id_staf_fo=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien?err={quote(f'Gagal buat kunjungan: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    data = result.get("data", {}) if isinstance(result, dict) else {}
    new_id_kunjungan = data.get("id_kunjungan")
    nomor_antrean = data.get("nomor_antrean", "?")
    if not new_id_kunjungan:
        return RedirectResponse(
            url=f"/web/pasien?err={quote('Kunjungan dibuat tapi id_kunjungan tidak diketahui.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Step 2: Pakai sesi series → konversi rencana PENDING → SCHEDULED + buat kunjungan_tindakan
    try:
        SeriesService(db).use_session(
            id_rencana=id_rencana,
            id_kunjungan=new_id_kunjungan,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien?err={quote(f'Kunjungan #{new_id_kunjungan} dibuat tapi pakai sesi gagal: {e.detail!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien?err={quote(f'Kunjungan #{new_id_kunjungan} dibuat tapi pakai sesi gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    msg = (
        f"Pasien masuk Ruang Tindakan untuk lanjut series {nama_tindakan} "
        f"sesi {urutan_sesi}, nomor antrian #{nomor_antrean}."
    )
    return RedirectResponse(
        url=f"/web/pasien?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# GET /web/pasien/{id_pasien}/beli-produk
# FO flow tanpa konsultasi: form pilih produk.
# Restored after B-009 truncation (6 Jun 2026).
# =============================================================================
@router.get("/pasien/{id_pasien}/beli-produk", response_class=HTMLResponse)
def pasien_beli_produk_form(
    id_pasien: int,
    request: Request,
    db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    pasien_svc = PasienService(db)
    pasien = pasien_svc.pasien_repo.get_by_id(id_pasien)
    if pasien is None:
        return RedirectResponse(
            url="/web/pasien?err=Pasien+tidak+ditemukan",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    from app.services.master_produk_service import MasterProdukService
    master_produks = MasterProdukService(db).list_all(only_active=True, limit=500)

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/pasien",
        page_subtitle=f"Beli Produk - {pasien.nama}",
    )
    # M2: warning lunak kalau pasien punya membership BELUM aktif (PENDING/PAID) →
    # produk dibayar tanpa diskon member. Tidak memblok (SOP/training).
    from app.db.models import PasienMembershipHistory as _PMH, StatusAktivasiEnum as _SA
    _pend_mship = (
        db.query(_PMH)
        .filter(_PMH.id_pasien == id_pasien)
        .filter(_PMH.status_aktivasi.in_([_SA.PENDING, _SA.PAID]))
        .first()
    )
    membership_warning = (
        "Pasien punya membership yang BELUM diaktifkan. Produk ini dibayar TANPA "
        "diskon member sampai membership dibayar & diaktifkan CS."
    ) if _pend_mship is not None else None

    ctx.update({
        "pasien": pasien,
        "master_produks": master_produks,
        "error": request.query_params.get("err"),
        "membership_warning": membership_warning,
    })
    return templates.TemplateResponse(request, "pasien_beli_produk.html", ctx)


# =============================================================================
# POST /web/pasien/{id_pasien}/beli-produk
# Submit form beli produk → call KunjunganService.beli_produk_lengkap.
# =============================================================================
@router.post("/pasien/{id_pasien}/beli-produk")
async def pasien_beli_produk_submit(
    id_pasien: int,
    request: Request,
    db: DbSession,
):
    from urllib.parse import quote

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 — Forbidden.</div>",
            status_code=403,
        )

    # Parse form (multi-row produk)
    form = await request.form()
    keluhan_utama = (form.get("keluhan_utama") or "").strip()
    id_produk_list = form.getlist("id_produk")
    qty_list = form.getlist("qty")
    aturan_list = form.getlist("aturan_pakai")

    produk_list = []
    for i, id_p in enumerate(id_produk_list):
        if not id_p:
            continue
        try:
            produk_list.append({
                "id_produk": int(id_p),
                "qty": float(qty_list[i]) if i < len(qty_list) and qty_list[i] else 1.0,
                "aturan_pakai": aturan_list[i] if i < len(aturan_list) else "",
            })
        except (ValueError, IndexError):
            continue

    if not produk_list:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/beli-produk?err={quote('Minimal 1 produk wajib dipilih.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        result = KunjunganService(db).beli_produk_lengkap(
            id_pasien=id_pasien,
            produk_list=produk_list,
            id_staf_fo=user.id_staf,
            keluhan_utama=keluhan_utama,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/beli-produk?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/beli-produk?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # FIX BUG-T4 (10 Juni 2026): tanpa success redirect, FastAPI return None →
    # serialized as JSON "null" sehingga user lihat halaman "null".
    nomor_antrean = (result.get("data") or {}).get("nomor_antrean", "?")
    msg = f"Pasien didaftarkan beli produk. No.antrean #{nomor_antrean}, langsung ke kasir."
    return RedirectResponse(
        url=f"/web/kunjungan?ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TODO-NEW-1 #29A — Alergi CRUD dokter access (dari Detail Pasien page)
# =============================================================================
def _alergi_can_edit(user) -> bool:
    role = (user.role.value if hasattr(user.role, "value") else str(user.role)).upper()
    return role in {"DOKTER", "ADMIN", "OWNER", "SUPERADMIN"}


@router.post("/pasien/{id_pasien}/alergi/tambah", response_class=HTMLResponse)
async def pasien_alergi_tambah(
    id_pasien: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403 - Hanya Dokter/Owner</div>", status_code=403)
    form = await request.form()
    alergen = (form.get("alergen") or "").strip()
    gejala = (form.get("gejala") or "").strip()
    tingkat = (form.get("tingkat_keparahan") or "RINGAN").strip().upper()
    if not alergen:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Alergen%20wajib%20diisi",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = AlergiAddRequest(
            id_pasien=id_pasien,
            alergen=alergen,
            gejala=gejala,
            tingkat_keparahan=TingkatKeparahanAlergiEnum[tingkat],  # name lookup ("RINGAN"/"SEDANG"/"BERAT")
        )
        PasienService(db).tambah_alergi(payload, id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Alergi%20ditambahkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/alergi/{id_alergi}/ubah", response_class=HTMLResponse)
async def pasien_alergi_ubah(
    id_pasien: int, id_alergi: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    alergen = (form.get("alergen") or "").strip() or None
    gejala = form.get("gejala")
    tingkat_str = (form.get("tingkat_keparahan") or "").strip().upper()
    tingkat_enum = TingkatKeparahanAlergiEnum[tingkat_str] if tingkat_str else None
    try:
        payload = AlergiUpdateRequest(
            alergen=alergen, gejala=gejala, tingkat_keparahan=tingkat_enum,
        )
        PasienService(db).update_alergi(
            id_alergi=id_alergi, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Alergi%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/alergi/{id_alergi}/hapus", response_class=HTMLResponse)
def pasien_alergi_hapus(
    id_pasien: int, id_alergi: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        PasienService(db).hapus_alergi(
            id_alergi=id_alergi, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Alergi%20dihapus",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TODO-NEW-1 #29B - Penyakit Kronis CRUD dari Detail Pasien
# =============================================================================
@router.post("/pasien/{id_pasien}/penyakit-kronis/tambah", response_class=HTMLResponse)
async def pasien_penyakit_kronis_tambah(
    id_pasien: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    nama = (form.get("nama_penyakit") or "").strip()
    catatan = (form.get("catatan") or "").strip()
    if not nama:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Nama%20penyakit%20wajib%20diisi",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = PenyakitKronisAddRequest(
            id_pasien=id_pasien, nama_penyakit=nama, catatan=catatan,
        )
        PasienService(db).tambah_penyakit_kronis(payload, id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Penyakit%20kronis%20ditambahkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/penyakit-kronis/{id_penyakit}/ubah", response_class=HTMLResponse)
async def pasien_penyakit_kronis_ubah(
    id_pasien: int, id_penyakit: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    nama = (form.get("nama_penyakit") or "").strip() or None
    catatan = form.get("catatan")
    try:
        payload = PenyakitKronisUpdateRequest(nama_penyakit=nama, catatan=catatan)
        PasienService(db).update_penyakit_kronis(
            id_penyakit=id_penyakit, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Penyakit%20kronis%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/penyakit-kronis/{id_penyakit}/hapus", response_class=HTMLResponse)
def pasien_penyakit_kronis_hapus(
    id_pasien: int, id_penyakit: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        PasienService(db).hapus_penyakit_kronis(
            id_penyakit=id_penyakit, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Penyakit%20kronis%20dihapus",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TODO-NEW-1 #29C-ext - Antropometri edit dari Detail Pasien (dokter access)
# =============================================================================
@router.post("/pasien/{id_pasien}/antropometri/{id_kunjungan}/ubah", response_class=HTMLResponse)
async def pasien_antropometri_ubah(
    id_pasien: int, id_kunjungan: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()

    def _to_float(key):
        raw = (form.get(key) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    try:
        payload = AntropometriUpsertRequest(
            id_kunjungan=id_kunjungan,
            berat_badan=_to_float("berat_badan"),
            tinggi_badan=_to_float("tinggi_badan"),
            tekanan_darah=(form.get("tekanan_darah") or "").strip(),
            suhu_tubuh=_to_float("suhu_tubuh"),
            skinfold_titik_1=_to_float("skinfold_titik_1"),
            skinfold_titik_2=_to_float("skinfold_titik_2"),
            skinfold_titik_3=_to_float("skinfold_titik_3"),
            lingkar_perut=_to_float("lingkar_perut"),
        )
        AntropometriService(db).upsert(payload, id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Antropometri%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# AN-L2c - Antropometri AI (modul eksternal): buat laporan (fire-and-forget) + resend
# =============================================================================
def _antro_can_create(user) -> bool:
    role = (user.role.value if hasattr(user.role, "value") else str(user.role)).upper()
    return role in {"DOKTER", "PERAWAT", "ADMIN", "OWNER", "SUPERADMIN"}


def _antro_back(return_to: str, id_pasien: int, *, err: str = "", ok: str = ""):
    import urllib.parse as _up
    base = (return_to or f"/web/pasien/{id_pasien}").strip()
    if not base.startswith("/"):
        base = f"/web/pasien/{id_pasien}"
    q = ""
    if err:
        q = "?err=" + _up.quote(err)
    elif ok:
        q = "?ok=" + _up.quote(ok)
    return RedirectResponse(url=base + q, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/pasien/{id_pasien}/antro/buat", response_class=HTMLResponse)
async def pasien_antro_buat(id_pasien: int, request: Request, db: DbSession):
    """Fire-and-forget: rakit intake identitas (tanpa ukuran) -> POST modul /intake ->
    arahkan browser ke form modul (pre-fill). Ukuran diisi di modul, bukan di Sehati."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _antro_can_create(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    return_to = (form.get("return_to") or f"/web/pasien/{id_pasien}").strip()
    if not AntroReportService.enabled():
        return _antro_back(return_to, id_pasien, err="Modul antropometri belum aktif.")
    from app.db.models import Pasien
    pasien = db.get(Pasien, id_pasien)
    if pasien is None:
        return _antro_back(return_to, id_pasien, err="Pasien tidak ditemukan.")
    base = str(request.base_url).rstrip("/")
    return_url = base + (return_to if return_to.startswith("/") else f"/web/pasien/{id_pasien}")
    svc = AntroReportService(db)
    try:
        import time as _time
        # Key UNIK per klik "Buat" -> modul membuat assessment BARU (balas /intake, bukan /review laporan
        # lama). Resolusi detik = double-submit dlm 1 detik tetap idempoten (aman dari klik ganda).
        idem = f"sehati-antro-{id_pasien}-{int(_time.time())}"
        payload = svc.build_payload(
            pasien=pasien, antro=None,
            actor_role=(user.role.value if hasattr(user.role, "value") else str(user.role)),
            actor_staf_id=user.id_staf, actor_name=user.nama_staf, return_url=return_url,
            idempotency_key=idem,
        )
        res = svc.kirim(payload)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "refused" in msg.lower() or "urlopen" in msg.lower() or "timed out" in msg.lower():
            msg = "Modul antropometri sedang tidak aktif. Nyalakan modul (run_web) lalu coba lagi."
        return _antro_back(return_to, id_pasien, err=msg)
    url = (res or {}).get("url")
    if not url:
        return _antro_back(return_to, id_pasien, err="Modul tak mengembalikan URL form.")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/pasien/{id_pasien}/antro/{assessment_id}/resend", response_class=HTMLResponse)
async def pasien_antro_resend(id_pasien: int, assessment_id: str, request: Request, db: DbSession):
    """Minta modul buat ulang laporan yang GAGAL (re-send). Baca-saja bagi Sehati."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _antro_can_create(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    return_to = (form.get("return_to") or f"/web/pasien/{id_pasien}").strip()
    if not AntroReportService.enabled():
        return _antro_back(return_to, id_pasien, err="Modul antropometri belum aktif.")
    try:
        AntroReportService(db).resend(assessment_id)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "refused" in msg.lower() or "urlopen" in msg.lower() or "timed out" in msg.lower():
            msg = "Modul antropometri sedang tidak aktif. Nyalakan modul lalu coba lagi."
        return _antro_back(return_to, id_pasien, err=f"Gagal minta ulang: {msg}")
    return _antro_back(return_to, id_pasien, ok="Laporan diminta ulang. Pantau statusnya.")


# =============================================================================
# TODO-NEW-6 #50 - Edit profile pasien (nama, tgl_lahir, alamat, telepon, KTP, email, membership)
# =============================================================================
@router.post("/pasien/{id_pasien}/edit", response_class=HTMLResponse)
async def pasien_edit_submit(
    id_pasien: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    # Permission: FO + Admin + Owner + Superadmin (ANTRIAN_MGMT_ROLES)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 - Hanya FO/Admin/Owner yang bisa edit profile pasien.</div>",
            status_code=403,
        )
    form = await request.form()

    def _str_or_none(key: str):
        raw = (form.get(key) or "").strip()
        return raw if raw else None

    def _date_or_none(key: str):
        raw = (form.get(key) or "").strip()
        if not raw:
            return None
        try:
            from datetime import date as _date
            return _date.fromisoformat(raw)
        except (TypeError, ValueError):
            return None

    try:
        # Parse enum fields
        jk_str = (form.get("jenis_kelamin") or "").strip().upper()
        jk = GenderEnum(jk_str) if jk_str in ("L", "P") else None

        tm_str = (form.get("tipe_membership") or "").strip().upper()
        tm = MembershipTierEnum(tm_str) if tm_str in ("REGULAR", "VIP", "VVIP") else None

        payload = PasienUpdateRequest(
            nama=_str_or_none("nama"),
            jenis_kelamin=jk,
            tgl_lahir=_date_or_none("tgl_lahir"),
            alamat=_str_or_none("alamat"),
            nomor_telepon=_str_or_none("nomor_telepon"),
            nomor_ktp=_str_or_none("nomor_ktp"),
            email_address=_str_or_none("email_address"),
            sumber_referensi=_str_or_none("sumber_referensi"),
            tipe_membership=tm,
        )
        PasienService(db).update_pasien_profile(
            id_pasien=id_pasien, payload=payload,
            actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}?ok=Profile%20pasien%20berhasil%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# #362E - Section Membership: page + actions
# =============================================================================
@router.get("/pasien/{id_pasien}/membership", response_class=HTMLResponse)
def pasien_membership_page(id_pasien: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    # Akses: semua role bisa view (FO, kasir, dokter, owner)
    try:
        status_data = MembershipService(db).get_status_pasien(id_pasien)
    except HTTPException as e:
        return HTMLResponse(
            f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>",
            status_code=e.status_code,
        )
    # Permission untuk action: ANTRIAN_MGMT (FO + Admin + Owner + Superadmin)
    can_manage = require_antrian_mgmt_role(user)
    ctx = build_shell_context(
        user, db=db, current_path="/web/pasien",
        page_subtitle=f"Membership - {status_data['pasien']['nama']}",
        status_data=status_data,
        can_manage=can_manage,
        flash=request.query_params.get("ok"),
        flash_error=request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, "pasien_membership.html", ctx)


@router.post("/pasien/{id_pasien}/membership/aktivasi", response_class=HTMLResponse)
async def pasien_membership_aktivasi(id_pasien: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    id_membership_str = (form.get("id_membership") or "").strip()
    action_type = (form.get("action_type") or "ACTIVATION").strip().upper()
    if not id_membership_str.isdigit():
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err=Tier%20tidak%20valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        MembershipService(db).create_pending(
            id_pasien=id_pasien,
            id_membership=int(id_membership_str),
            actor_id_staf=user.id_staf,
            action_type=action_type,
            request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=(
            f"/web/pasien/{id_pasien}/membership"
            f"?ok=Pending%20{action_type}%20dibuat.%20Pasien%20bayar%20di%20kasir%20saat%20kunjungan%20berikutnya."
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/membership/{id_history}/cancel", response_class=HTMLResponse)
def pasien_membership_cancel(
    id_pasien: int, id_history: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        MembershipService(db).cancel_pending(
            id_history=id_history, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/pasien/{id_pasien}/membership?ok=Pending%20dibatalkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/membership/create-billing", response_class=HTMLResponse)
def pasien_membership_create_billing(
    id_pasien: int, request: Request, db: DbSession,
):
    """FIX-362E-B: Buat kunjungan ANTRI_BAYAR untuk pending membership tanpa konsul."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_antrian_mgmt_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    # M2: TIDAK lagi membuat kunjungan kosong. Membership PENDING otomatis muncul di
    # Antrian Kasir (seksi "Membership — Menunggu Pembayaran"). Route dipertahankan
    # sebagai no-op (kompat tombol/bookmark lama) → arahkan balik dgn info.
    return RedirectResponse(
        url=(
            f"/web/pasien/{id_pasien}/membership"
            f"?ok=Pending%20sudah%20otomatis%20muncul%20di%20Antrian%20Kasir%20(seksi%20Membership)."
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pasien/{id_pasien}/membership/{id_history}/aktifkan", response_class=HTMLResponse)
def pasien_membership_aktifkan(
    id_pasien: int, id_history: int, request: Request, db: DbSession,
):
    """M3: CS aktivasi membership PAID -> ACTIVE (+ no_member + kuota).
    Role §9: FO+Kasir+Admin+Owner+Superadmin."""
    from urllib.parse import quote
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not (require_antrian_mgmt_role(user) or require_kasir_role(user)):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        result = MembershipService(db).activate_membership(
            id_history=id_history, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err={quote(str(e.detail))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}/membership?err={quote(f'Gagal: {e!s}')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    _no = result.get("no_member") or "-"
    _tier = result.get("nama_tier") or ""
    msg = f"Membership {_tier} AKTIF. Nomor member: {_no}."
    _next = (request.query_params.get("next") or "").strip()
    _dest = _next if _next.startswith("/web/") else f"/web/pasien/{id_pasien}/membership"
    _sep = "&" if "?" in _dest else "?"
    return RedirectResponse(
        url=f"{_dest}{_sep}ok={quote(msg)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# Penyakit Kronis — SET (checkbox dari master + Lain-lain). Reconcile via service.
# =============================================================================
@router.post("/pasien/{id_pasien}/penyakit-kronis/set", response_class=HTMLResponse)
async def pasien_penyakit_kronis_set(id_pasien: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _alergi_can_edit(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    nxt = (form.get("next") or f"/web/pasien/{id_pasien}").strip()
    codes = []
    for k in form.getlist("kode"):
        try:
            codes.append(int(k))
        except (TypeError, ValueError):
            pass
    others = [t.strip() for t in form.getlist("lain_lain") if (t or "").strip()]
    try:
        PenyakitKronisService(db).set_state(id_pasien, codes, others, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"{nxt}?err={e.detail}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url=f"{nxt}?err=Gagal:%20{e!s}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"{nxt}?ok=Penyakit%20kronis%20disimpan", status_code=status.HTTP_303_SEE_OTHER)
