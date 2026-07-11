"""
Pendaftaran Pasien Baru — 4-step wizard (FO + Admin + Owner/Superadmin):
- GET  /web/pendaftaran-pasien                       — render wizard (kosong / flash)
- GET  /web/pendaftaran-pasien/_alergi-row           — HTMX partial: 1 row alergi
- GET  /web/pendaftaran-pasien/_penyakit-row         — HTMX partial: 1 row penyakit
- POST /web/pendaftaran-pasien                       — submit form (atomic via PasienService)

Service handles atomic create: pasien + alergi + penyakit + kunjungan + antropometri.
Default status_antrian = ANTRI_KONSULTASI, keluhan_utama = "" (diisi dokter saat konsultasi).
"""

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.db.models._enums import (
    GenderEnum,
    MembershipTierEnum,
    TingkatKeparahanAlergiEnum,
)
from app.schemas.pasien import (
    AlergiCreate,
    PasienBaruRequest,
    PenyakitKronisCreate,
)
from app.services.pasien_service import PasienService
from app.services.master_membership_service import MasterMembershipService
from app.web.routes._shared import (
    build_shell_context,
    get_dokter_aktif_list,
    get_user_from_cookie,
    templates,
)


router = APIRouter(tags=["Web Pendaftaran Pasien"])


# =============================================================================
# GET /web/pendaftaran-pasien — render wizard
# =============================================================================
@router.get("/pendaftaran-pasien", response_class=HTMLResponse)
def pendaftaran_pasien_form(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    # Flash dari query string setelah redirect dari sukses
    success = None
    ok_msg = request.query_params.get("ok")
    if ok_msg:
        success = {
            "message": ok_msg,
            "no_rm": request.query_params.get("no_rm", "-"),
            "id_pasien": request.query_params.get("id_pasien", ""),
            "nomor_antrean": request.query_params.get("antrean", "-"),
        }

    # #362C - Read tier aktif dari master_membership
    try:
        tiers_active = MasterMembershipService(db).list_all(only_active=True, limit=100)
        available_tiers = [
            {"nama_tier": t.nama_tier, "diskon_treatment": float(t.diskon_treatment_persen or 0),
             "diskon_produk": float(t.diskon_produk_persen or 0), "harga_aktivasi": float(t.harga_aktivasi or 0)}
            for t in tiers_active
        ]
    except Exception:
        available_tiers = []

    ctx = build_shell_context(
        user,
        db=db,
        current_path="/web/pendaftaran-pasien",
        page_subtitle="Wizard 4-step",
        form={},
        error=None,
        success=success,
        available_tiers=available_tiers,
        # FO-ASSIGN-DOKTER (Task #329): list dokter aktif untuk dropdown
        dokter_list=get_dokter_aktif_list(db),
    )
    return templates.TemplateResponse(request, "pendaftaran_pasien.html", ctx)


# =============================================================================
# GET partials — fresh row untuk alergi & penyakit
# =============================================================================
@router.get("/pendaftaran-pasien/_alergi-row", response_class=HTMLResponse)
def pendaftaran_alergi_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    return templates.TemplateResponse(request, "_alergi_row.html", {})


@router.get("/pendaftaran-pasien/_penyakit-row", response_class=HTMLResponse)
def pendaftaran_penyakit_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    return templates.TemplateResponse(request, "_penyakit_row.html", {})


# =============================================================================
# POST /web/pendaftaran-pasien — submit wizard
# =============================================================================
@router.post("/pendaftaran-pasien", response_class=HTMLResponse)
async def pendaftaran_pasien_submit(request: Request, db: DbSession):
    """
    Parse form (multi-row alergi & penyakit), build PasienBaruRequest,
    call PasienService.register_pasien_baru (atomic).
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    form_data = await request.form()

    def _re_render(error_msg: str):
        ctx = build_shell_context(
            user,
            db=db,
            current_path="/web/pendaftaran-pasien",
            page_subtitle="Wizard 4-step",
            form=dict(form_data),
            error=error_msg,
            success=None,
            dokter_list=get_dokter_aktif_list(db),
        )
        return templates.TemplateResponse(request, "pendaftaran_pasien.html", ctx)

    # ---- Step 1: Identitas ----
    nama = (form_data.get("nama") or "").strip()
    jk_raw = form_data.get("jenis_kelamin") or ""
    if not nama:
        return _re_render("Nama wajib diisi.")
    try:
        jenis_kelamin = GenderEnum(jk_raw)
    except ValueError:
        return _re_render(f"Jenis kelamin tidak valid: {jk_raw}")

    tgl_lahir_raw = form_data.get("tgl_lahir") or ""
    tgl_lahir = None
    if tgl_lahir_raw:
        try:
            tgl_lahir = date.fromisoformat(tgl_lahir_raw)
        except ValueError:
            return _re_render(f"Tanggal lahir tidak valid: {tgl_lahir_raw}")

    # ---- Step 2: Sumber + Membership ----
    membership_raw = form_data.get("tipe_membership") or "REGULAR"
    try:
        tipe_membership = MembershipTierEnum(membership_raw)
    except ValueError:
        return _re_render(f"Tipe membership tidak valid: {membership_raw}")

    # ---- Step 3: Alergi (multi) ----
    alergens = form_data.getlist("alergen")
    alergi_gejalas = form_data.getlist("alergi_gejala")
    alergi_tingkats = form_data.getlist("alergi_tingkat")
    alergi_list = []
    for i, alergen in enumerate(alergens):
        alergen_str = (alergen or "").strip()
        if not alergen_str:
            continue
        tingkat_raw = alergi_tingkats[i] if i < len(alergi_tingkats) else "Ringan"
        try:
            tingkat = TingkatKeparahanAlergiEnum(tingkat_raw)
        except ValueError:
            tingkat = TingkatKeparahanAlergiEnum.RINGAN
        gejala = alergi_gejalas[i] if i < len(alergi_gejalas) else ""
        alergi_list.append(AlergiCreate(
            alergen=alergen_str,
            gejala=(gejala or "").strip(),
            tingkat_keparahan=tingkat,
        ))

    # ---- Step 3: Penyakit kronis (multi) ----
    nama_penyakits = form_data.getlist("nama_penyakit")
    penyakit_catatans = form_data.getlist("penyakit_catatan")
    penyakit_list = []
    for i, np in enumerate(nama_penyakits):
        np_str = (np or "").strip()
        if not np_str:
            continue
        catatan = penyakit_catatans[i] if i < len(penyakit_catatans) else ""
        penyakit_list.append(PenyakitKronisCreate(
            nama_penyakit=np_str,
            catatan=(catatan or "").strip(),
        ))

    # ---- Antropometri & tanda vital: PINDAH ke modul Antropometri AI (AN-L2c). ----
    # Sehati tidak lagi menangkap pengukuran fisik saat pendaftaran.

    # FO-ASSIGN-DOKTER (Task #329): parse id_staf_dokter_assigned dari form
    id_dokter_assigned_raw = (form_data.get("id_staf_dokter_assigned") or "").strip()
    id_dokter_assigned = None
    if id_dokter_assigned_raw:
        try:
            id_dokter_assigned = int(id_dokter_assigned_raw)
            if id_dokter_assigned < 1:
                id_dokter_assigned = None
        except ValueError:
            id_dokter_assigned = None

    # ---- Build payload ----
    try:
        payload = PasienBaruRequest(
            nama=nama,
            jenis_kelamin=jenis_kelamin,
            alamat=(form_data.get("alamat") or "").strip(),
            tgl_lahir=tgl_lahir,
            nomor_telepon=(form_data.get("nomor_telepon") or "").strip(),
            nomor_ktp=(form_data.get("nomor_ktp") or "").strip(),
            sumber_referensi=(form_data.get("sumber_referensi") or "").strip(),
            email_address=(form_data.get("email_address") or "").strip(),
            tipe_membership=tipe_membership,
            status_antrian="ANTRI_KONSULTASI",
            keluhan_utama="",
            id_staf_dokter_assigned=id_dokter_assigned,
            alergi=alergi_list,
            penyakit_kronis=penyakit_list,
            antropometri=None,
        )
    except Exception as e:
        return _re_render(f"Data tidak valid: {e!s}")

    # ---- Call service (atomic — commit/rollback handled di service) ----
    # action menentukan apakah pasien langsung masuk antrian:
    #   "daftar-sekarang" -> buat kunjungan (masuk antrian)
    #   "simpan"          -> simpan pasien SAJA tanpa antrian (pre-registrasi)
    action = (form_data.get("action") or "simpan").strip()
    try:
        result = PasienService(db).register_pasien_baru(
            payload=payload,
            id_staf_fo=user.id_staf,
            request=request,
            buat_kunjungan=(action == "daftar-sekarang"),
        )
    except HTTPException as e:
        return _re_render(e.detail)
    except Exception as e:
        return _re_render(f"Gagal menyimpan: {e!s}")

    # ---- Sukses — redirect by action button ----
    data = result.get("data", {})
    no_rm = data.get("no_rm", "-")
    id_pasien = data.get("id_pasien", "")
    antrean = data.get("nomor_antrean", "-")

    if action == "daftar-sekarang" and id_pasien:
        # Masuk antrian → buka detail pasien + auto-cetak nomor antrian
        _idk = data.get("id_kunjungan")
        _pp = f"?print_antrian={_idk}" if _idk else ""
        return RedirectResponse(
            url=f"/web/pasien/{id_pasien}{_pp}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # action=simpan → pasien disimpan TANPA antrian. Flash + kembali ke form.
    msg = (
        f"Pasien '{nama}' (RM {no_rm}) disimpan tanpa antrian. "
        f"Untuk memasukkan ke antrian, buka Cari Pasien lalu +Antrian."
    )
    qs = urlencode({"ok": msg, "no_rm": no_rm, "id_pasien": id_pasien})
    return RedirectResponse(
        url=f"/web/pendaftaran-pasien?{qs}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
