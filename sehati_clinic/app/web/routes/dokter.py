"""
Antrian Dokter:
- GET /web/dokter/antrian, /antrian/list
- GET /web/dokter/kunjungan/{id}/soap (form)
- POST /web/dokter/kunjungan/{id}/soap (submit)
- GET /web/dokter/_tindakan-row, /_resep-row (HTMX partials)
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.repositories.pemeriksaan_repo import PemeriksaanRepository
from app.repositories.treatment_repo import TreatmentRepository
from app.schemas.pemeriksaan import (
    InputMedisRequest,
    ResepProdukItem,
    TindakanBaruItem,
)
from app.services.antropometri_service import AntropometriService
from app.services.antro_report_service import AntroReportService
from app.services.diagnosa_service import DiagnosaService
from app.schemas.antropometri import AntropometriUpsertRequest
from app.services.kunjungan_service import KunjunganService
from app.services.master_produk_service import MasterProdukService
from app.services.pasien_service import PasienService
from app.services.penyakit_kronis_service import PenyakitKronisService
from app.schemas.pasien import AlergiAddRequest, AlergiUpdateRequest, PenyakitKronisAddRequest, PenyakitKronisUpdateRequest
from app.db.models import TingkatKeparahanAlergiEnum
from app.services.pemeriksaan_service import PemeriksaanService
from app.web.routes._shared import (
    render_cached,
    build_shell_context,
    get_user_from_cookie,
    require_dokter_antrian_role,
    templates,
)


router = APIRouter(tags=["Web Dokter"])


@router.get("/dokter/antrian", response_class=HTMLResponse)
def dokter_antrian_page(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_dokter_antrian_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    ctx = build_shell_context(user, db=db, current_path="/web/dokter/antrian", page_subtitle="Auto-refresh 10s")
    return templates.TemplateResponse(request, "dokter_antrian.html", ctx)


@router.get("/dokter/antrian/list", response_class=HTMLResponse)
def dokter_antrian_partial(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Sesi habis.</div>", status_code=401)
    if not require_dokter_antrian_role(user):
        return HTMLResponse("<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>403</div>", status_code=403)
    def _build():
        # SOAP-GUARD scoping (Decision A): filter antrian per id_staf_dokter.
        antrian_resp = PemeriksaanService(db).lihat_antrian_dokter(id_staf_dokter=user.id_staf)
        antrian_dict = antrian_resp.model_dump()
        counter_dict = antrian_dict.get("counter", {})
        for item in antrian_dict.get("data", []):
            if item.get("jenis_kelamin") and hasattr(item["jenis_kelamin"], "value"):
                item["jenis_kelamin"] = item["jenis_kelamin"].value
        return templates.TemplateResponse(request, "_dokter_antrian_content.html", {"antrian": antrian_dict, "counter": counter_dict})
    try:
        # CACHE tampilan (KESTABILAN §9): kunci per-dokter; auth sudah dicek di atas.
        from app.core.ttl_cache import ANTRIAN_TTL
        return render_cached(f"antrian:dokter:{user.id_staf}", ANTRIAN_TTL, _build)
    except Exception as e:
        return HTMLResponse(f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>Error: {e!s}</div>", status_code=500)


def _fetch_master_lists(db):
    treatments = TreatmentRepository(db).list_master_active(limit=500)
    produks = MasterProdukService(db).list_all(only_active=True, limit=500)
    return treatments, produks


def _build_soap_ctx(db, user, id_kunjungan: int, form_data: dict, error=None):
    kunjungan_detail = KunjunganService(db).get_detail(id_kunjungan)
    kunjungan_dict = kunjungan_detail.model_dump()
    # modul #7: prefill field kontrol dari ORM (DTO detail belum tentu memuatnya)
    try:
        from app.db.models.kunjungan import Kunjungan as _KjModel
        _kj_row = db.get(_KjModel, id_kunjungan)
        if _kj_row is not None:
            kunjungan_dict["tgl_kontrol_selanjutnya"] = _kj_row.tgl_kontrol_selanjutnya
            kunjungan_dict["catatan_kontrol"] = _kj_row.catatan_kontrol
    except Exception:
        pass
    id_pasien = kunjungan_dict["id_pasien"]

    is_edit_mode = False
    existing_tindakan: list = []
    existing_resep: list = []
    existing_series: list = []
    pemeriksaan_repo = PemeriksaanRepository(db)
    if not any(form_data.values() if form_data else []):
        existing_soap = pemeriksaan_repo.get_latest_soap_by_kunjungan(id_kunjungan)
        if existing_soap is not None:
            form_data = {
                "anamnesa": existing_soap.anamnesa or "",
                "pemeriksaan_fisik": existing_soap.pemeriksaan_fisik or "",
                "diagnosa": existing_soap.diagnosa or "",
            }
            is_edit_mode = True

    # Fetch existing tindakan + resep + series untuk display di Ubah mode
    if is_edit_mode:
        for tindakan, treatment in pemeriksaan_repo.get_tindakan_by_kunjungan(id_kunjungan):
            existing_tindakan.append({
                "nama_treatment": treatment.nama_treatment,
                "harga": float(treatment.harga) if treatment.harga else 0,
                "status_tindakan": (
                    tindakan.status_tindakan.value
                    if tindakan.status_tindakan and hasattr(tindakan.status_tindakan, "value")
                    else str(tindakan.status_tindakan or "PENDING")
                ),
            })
        for rencana in pemeriksaan_repo.get_rencana_series_by_kunjungan(id_kunjungan):
            existing_series.append({
                "nama_tindakan": rencana.nama_tindakan,
                "urutan_sesi": rencana.urutan_sesi,
                "status": (
                    rencana.status.value
                    if rencana.status and hasattr(rencana.status, "value")
                    else str(rencana.status or "PENDING")
                ),
                "catatan_dokter": rencana.catatan_dokter or "",
            })
        for resep, produk in pemeriksaan_repo.get_resep_by_kunjungan(id_kunjungan):
            existing_resep.append({
                "nama_produk": produk.nama_produk,
                "kode_produk": produk.kode_produk,
                "qty": float(resep.qty) if resep.qty else 0,
                "aturan_pakai": resep.aturan_pakai or "",
                "status_item": (
                    resep.status_item.value
                    if resep.status_item and hasattr(resep.status_item, "value")
                    else str(resep.status_item or "PENDING")
                ),
            })

    pasien_detail = PasienService(db).get_detail(id_pasien)
    pasien_dict = pasien_detail.model_dump()
    if pasien_dict.get("jenis_kelamin") and hasattr(pasien_dict["jenis_kelamin"], "value"):
        pasien_dict["jenis_kelamin"] = pasien_dict["jenis_kelamin"].value
    if pasien_dict.get("tipe_membership") and hasattr(pasien_dict["tipe_membership"], "value"):
        pasien_dict["tipe_membership"] = pasien_dict["tipe_membership"].value
    for a in pasien_dict.get("alergi", []):
        if a.get("tingkat_keparahan") and hasattr(a["tingkat_keparahan"], "value"):
            a["tingkat_keparahan"] = a["tingkat_keparahan"].value

    try:
        antro_resp = AntropometriService(db).get_terakhir_with_clinical(id_pasien)
        antropometri_dict = antro_resp.model_dump()
    except Exception:
        antropometri_dict = {"has_data": False}

    treatments, produks = _fetch_master_lists(db)

    # P2-#3 - Build kuota map untuk indicator di tindakan dropdown
    # {id_treatment: {sisa, kuota_total, periode}}
    kuota_map = {}
    try:
        from app.services.membership_service import MembershipService as _MShip
        _kuota_list = _MShip(db).list_kuota_for_pasien(id_pasien=id_pasien)
        for k in _kuota_list:
            if k.get("sisa", 0) > 0:
                kuota_map[k["id_treatment"]] = {
                    "sisa": k["sisa"],
                    "kuota_total": k["kuota_total"],
                    "periode": k["periode_kuota"],
                }
    except Exception:
        kuota_map = {}

    # #4 Riwayat kunjungan (SOAP + tindakan + produk) untuk panel dokter. Read-only, fetch sekali.
    soap_history = []
    try:
        _riw = PasienService(db).get_riwayat(id_pasien, limit_kunjungan=30).model_dump()
        _dx = {}
        for _s, _d in pemeriksaan_repo.get_riwayat_soap(id_pasien, limit=60):
            _dx.setdefault(_s.id_kunjungan, {
                "diagnosa": (_s.diagnosa or _s.anamnesa or ""),
                "dokter": (_d.nama_staf if _d else None),
            })
        _visits: dict = {}
        for _t in _riw.get("riwayat_tindakan_diresepkan", []):
            _kj = _t.get("id_kunjungan")
            if _kj is None:
                continue
            _v = _visits.setdefault(_kj, {"tanggal": _t.get("tgl_diresepkan"), "treatments": [], "products": []})
            if _t.get("tgl_diresepkan"):
                _v["tanggal"] = _t["tgl_diresepkan"]
            _nm = _t.get("nama_treatment")
            if _nm and _nm not in _v["treatments"]:
                _v["treatments"].append(_nm)
        for _p in _riw.get("produk_diresepkan", []):
            _kj = _p.get("id_kunjungan")
            if _kj is None:
                continue
            _v = _visits.setdefault(_kj, {"tanggal": _p.get("tgl_resep"), "treatments": [], "products": []})
            if _p.get("tgl_resep") and not _v.get("tanggal"):
                _v["tanggal"] = _p["tgl_resep"]
            _nm = _p.get("nama_produk")
            if _nm and _nm not in _v["products"]:
                _v["products"].append(_nm)
        for _kj, _v in _visits.items():
            if _kj == id_kunjungan:
                continue
            _tg = _v.get("tanggal")
            soap_history.append({
                "_k": _tg,
                "tanggal": (_tg.strftime("%d %b %Y") if hasattr(_tg, "strftime") else (str(_tg)[:10] if _tg else "-")),
                "dokter": _dx.get(_kj, {}).get("dokter"),
                "diagnosa": _dx.get(_kj, {}).get("diagnosa", ""),
                "treatments": _v["treatments"],
                "products": _v["products"],
            })
        soap_history.sort(key=lambda x: (x["_k"] is not None, x["_k"]), reverse=True)
        soap_history = soap_history[:15]
    except Exception:
        soap_history = []

    return build_shell_context(
        user,
        db=db,
        current_path="/web/dokter/antrian",
        page_subtitle=f"SOAP - {pasien_dict['nama']}",
        kunjungan=kunjungan_dict,
        pasien=pasien_dict,
        antropometri=antropometri_dict,
        antro_laporan=AntroReportService().laporan_by_rm(pasien_dict.get("no_rm")),
        kuota_map=kuota_map,
        form=form_data,
        error=error,
        is_edit_mode=is_edit_mode,
        master_treatments=treatments,
        master_produks=produks,
        existing_tindakan=existing_tindakan,
        existing_resep=existing_resep,
        existing_series=existing_series,
        existing_diagnosa=DiagnosaService(db).get_kunjungan_diagnosa(id_kunjungan),
        soap_history=soap_history,
        master_penyakit_list=PenyakitKronisService(db).list_master(),
    )


@router.get("/dokter/kunjungan/{id_kunjungan}/soap", response_class=HTMLResponse)
def dokter_soap_form_page(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_dokter_antrian_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        ctx = _build_soap_ctx(db, user, id_kunjungan, form_data={})
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)
    # V7.2.1 audit akses-baca SOAP
    try:
        from app.db.models import Kunjungan as _K
        from app.services.audit_service import AuditService as _AS
        _kunj = db.get(_K, id_kunjungan)
        if _kunj is not None:
            _AS(db).log_view(user.id_staf, _kunj.id_pasien,
                             keterangan=f"Buka SOAP kunjungan #{id_kunjungan}", request=request)
    except Exception:
        pass
    return templates.TemplateResponse(request, "dokter_soap_form.html", ctx)


@router.get("/dokter/_tindakan-row", response_class=HTMLResponse)
def dokter_tindakan_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    treatments, _ = _fetch_master_lists(db)
    return templates.TemplateResponse(request, "_tindakan_row.html", {"master_treatments": treatments})


@router.get("/dokter/_resep-row", response_class=HTMLResponse)
def dokter_resep_row(request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    _, produks = _fetch_master_lists(db)
    return templates.TemplateResponse(request, "_resep_row.html", {"master_produks": produks})


@router.get("/dokter/_diagnosa-search", response_class=HTMLResponse)
def dokter_diagnosa_search(request: Request, db: DbSession):
    """Autocomplete diagnosa (ICD + estetik) untuk picker SOAP."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    q = request.query_params.get("q", "")
    results = DiagnosaService(db).search(q, limit=15)
    return templates.TemplateResponse(request, "_diagnosa_search_results.html", {"results": results, "q": q})


@router.get("/dokter/_diagnosa-add/{id_diagnosa}", response_class=HTMLResponse)
def dokter_diagnosa_add(id_diagnosa: int, request: Request, db: DbSession):
    """Tambah 1 diagnosa ke SOAP → chip + auto-fill paket (OOB) + auto tgl kontrol."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    svc = DiagnosaService(db)
    try:
        ref = svc.get_ref(id_diagnosa)
    except HTTPException:
        return HTMLResponse("", status_code=404)
    dx = {
        "id_diagnosa": ref.id_diagnosa,
        "sistem": ref.sistem.value if hasattr(ref.sistem, "value") else ref.sistem,
        "kode": ref.kode, "nama": ref.nama,
        "default_kontrol_hari": ref.default_kontrol_hari,
    }
    return templates.TemplateResponse(request, "_diagnosa_add.html", {"dx": dx})


@router.get("/dokter/_saran", response_class=HTMLResponse)
def dokter_saran(request: Request, db: DbSession):
    """Panel saran = turunan dari daftar diagnosa saat ini + mode.

    Dirender ULANG setiap diagnosa berubah / mode berganti (event `dx-changed`),
    jadi tidak pernah basi atau menumpuk.
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    qp = request.query_params
    mode = (qp.get("fill_mode") or "SMART").upper()
    if mode == "MANUAL":
        return HTMLResponse("")

    ids = []
    for raw in qp.getlist("dx_id_diagnosa"):
        try:
            v = int(raw)
        except (ValueError, TypeError):
            continue
        if v not in ids:
            ids.append(v)
    if not ids:
        return HTMLResponse("")

    svc = DiagnosaService(db)
    tindakan, produk, seen = [], [], set()
    for did in ids:
        try:
            kode = svc.get_ref(did).kode
        except HTTPException:
            continue
        for it in svc.list_paket(did):
            if it["tipe_item"] == "TREATMENT" and it["id_treatment"]:
                key = ("T", it["id_treatment"])
                if key in seen:
                    continue
                seen.add(key)
                tindakan.append({
                    "tipe": "TREATMENT", "id": it["id_treatment"], "nama": it["nama"],
                    "qty": int(it["qty_default"] or 1), "aturan": "", "dari": kode,
                })
            elif it["tipe_item"] == "PRODUK" and it["id_produk"]:
                key = ("P", it["id_produk"])
                if key in seen:
                    continue
                seen.add(key)
                label = (f"[{it['kode_produk']}] " if it.get("kode_produk") else "") + it["nama"]
                produk.append({
                    "tipe": "PRODUK", "id": it["id_produk"], "nama": label,
                    "qty": it["qty_default"] or 1, "aturan": it["aturan_pakai_default"] or "",
                    "dari": kode,
                })
    if not tindakan and not produk:
        return HTMLResponse("")
    return templates.TemplateResponse(request, "_saran_panel.html", {
        "tindakan": tindakan, "produk": produk, "total": len(tindakan) + len(produk),
    })


@router.get("/dokter/_paket-apply", response_class=HTMLResponse)
def dokter_paket_apply(request: Request, db: DbSession):
    """Terapkan kartu saran terpilih → baris lengkap Tindakan/Resep (OOB) + kosongkan panel saran."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return HTMLResponse("", status_code=401)
    # Tiap kartu = 1 checkbox `sel` bernilai "TIPE|ID|QTY|ATURAN".
    # Toggle OFF → checkbox tidak terkirim → otomatis tidak diterapkan.
    paket_tindakan, paket_resep = [], []
    for raw in request.query_params.getlist("sel"):
        parts = (raw or "").split("|", 3)
        if len(parts) < 2:
            continue
        t = parts[0]
        try:
            _id = int(parts[1]) if str(parts[1]).strip() else None
        except (ValueError, TypeError):
            _id = None
        if not _id:
            continue
        raw_qty = parts[2] if len(parts) > 2 and str(parts[2]).strip() else "1"
        at = parts[3] if len(parts) > 3 else ""
        if (t or "").upper() == "TREATMENT":
            try:
                sesi = int(float(raw_qty))
            except (ValueError, TypeError):
                sesi = 1
            paket_tindakan.append({"id_treatment": _id, "jumlah_sesi": max(1, sesi), "catatan": ""})
        else:
            try:
                q = float(raw_qty)
            except (ValueError, TypeError):
                q = 1.0
            paket_resep.append({"id_produk": _id, "qty": q, "aturan": at})

    treatments, produks = _fetch_master_lists(db)
    return templates.TemplateResponse(request, "_paket_apply.html", {
        "paket_tindakan": paket_tindakan,
        "paket_resep": paket_resep,
        "master_treatments": treatments,
        "master_produks": produks,
        "kuota_map": {},
    })


@router.post("/dokter/kunjungan/{id_kunjungan}/soap", response_class=HTMLResponse)
async def dokter_soap_form_submit(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_dokter_antrian_role(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)

    form_data = await request.form()
    anamnesa = (form_data.get("anamnesa") or "").strip()
    pemeriksaan_fisik = (form_data.get("pemeriksaan_fisik") or "").strip()
    diagnosa = (form_data.get("diagnosa") or "").strip()

    form_state = {"anamnesa": anamnesa, "pemeriksaan_fisik": pemeriksaan_fisik, "diagnosa": diagnosa}

    def _re_render(error: str):
        ctx = _build_soap_ctx(db, user, id_kunjungan, form_state, error=error)
        return templates.TemplateResponse(request, "dokter_soap_form.html", ctx)

    try:
        kunjungan_detail = KunjunganService(db).get_detail(id_kunjungan)
        id_pasien = kunjungan_detail.id_pasien
    except HTTPException as e:
        return HTMLResponse(f"<div style='padding:2rem'>{e.status_code} - {e.detail}</div>", status_code=e.status_code)

    id_treatments = form_data.getlist("id_treatment")
    jumlah_sesis = form_data.getlist("jumlah_sesi")
    catatan_dokters = form_data.getlist("catatan_dokter")
    tindakan_list = []
    for i, id_t in enumerate(id_treatments):
        if not id_t or not str(id_t).strip():
            continue
        try:
            id_treatment = int(id_t)
        except (ValueError, TypeError):
            continue
        try:
            jumlah_sesi = int(jumlah_sesis[i]) if i < len(jumlah_sesis) else 1
        except (ValueError, TypeError):
            jumlah_sesi = 1
        catatan = catatan_dokters[i] if i < len(catatan_dokters) else ""
        is_series = jumlah_sesi > 1
        try:
            tindakan_list.append(TindakanBaruItem(
                id_treatment=id_treatment,
                is_series=is_series,
                jumlah_sesi=jumlah_sesi,
                catatan_dokter=(catatan or "").strip(),
            ))
        except Exception as e:
            return _re_render(f"Data tindakan tidak valid: {e!s}")

    id_produks = form_data.getlist("id_produk")
    qtys = form_data.getlist("qty")
    aturan_pakais = form_data.getlist("aturan_pakai")
    resep_list = []
    for i, id_p in enumerate(id_produks):
        if not id_p or not str(id_p).strip():
            continue
        try:
            id_produk = int(id_p)
        except (ValueError, TypeError):
            continue
        try:
            qty = float(qtys[i]) if i < len(qtys) else 1.0
        except (ValueError, TypeError):
            qty = 1.0
        aturan = aturan_pakais[i] if i < len(aturan_pakais) else ""
        try:
            resep_list.append(ResepProdukItem(
                id_produk=id_produk,
                qty=qty,
                aturan_pakai=(aturan or "").strip(),
            ))
        except Exception as e:
            return _re_render(f"Data resep tidak valid: {e!s}")

    try:
        payload = InputMedisRequest(
            id_kunjungan=id_kunjungan,
            id_pasien=id_pasien,
            anamnesa=anamnesa,
            pemeriksaan_fisik=pemeriksaan_fisik,
            diagnosa=diagnosa,
            saran_treatment="",
            saran_produk="",
            tindakan_baru=tindakan_list,
            resep_produk=resep_list,
        )
    except Exception as e:
        return _re_render(f"Data tidak valid: {e!s}")

    try:
        PemeriksaanService(db).input_medis_lengkap(
            payload=payload,
            id_staf_dokter=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return _re_render(e.detail)
    except Exception as e:
        return _re_render(f"Gagal: {e!s}")

    # modul #7: simpan rencana kontrol dokter + generate follow-up (G2+G3, satu commit)
    try:
        from datetime import date as _date
        from app.db.models.kunjungan import Kunjungan as _KjModel
        from app.services.followup_service import FollowupService
        _raw_tgl = (form_data.get("tgl_kontrol_selanjutnya") or "").strip()
        _tgl_kontrol = None
        if _raw_tgl:
            try:
                _tgl_kontrol = _date.fromisoformat(_raw_tgl)
            except ValueError:
                _tgl_kontrol = None
        _catatan_kontrol = (form_data.get("catatan_kontrol") or "").strip() or None

        # Diagnosa terstruktur (ICD + estetik, multi primer/sekunder) — modul #24–#27
        _dx_ids = form_data.getlist("dx_id_diagnosa")
        _dx_sis = form_data.getlist("dx_sistem")
        _dx_kode = form_data.getlist("dx_kode")
        _dx_nama = form_data.getlist("dx_nama")
        _dx_primer = form_data.getlist("dx_is_primer")
        _dx_entries = []
        for _i, _nm in enumerate(_dx_nama):
            if not (_nm or "").strip():
                continue
            try:
                _idd = int(_dx_ids[_i]) if _i < len(_dx_ids) and str(_dx_ids[_i]).strip() else None
            except (ValueError, TypeError):
                _idd = None
            _dx_entries.append({
                "id_diagnosa": _idd,
                "sistem": _dx_sis[_i] if _i < len(_dx_sis) else None,
                "kode": _dx_kode[_i] if _i < len(_dx_kode) else None,
                "nama": _nm,
                "is_primer": (_i < len(_dx_primer) and str(_dx_primer[_i]) == "1"),
            })
        # Selalu simpan (replace) — supaya penghapusan semua diagnosa di mode ubah ikut tersimpan.
        _primary_kontrol = DiagnosaService(db).save_kunjungan_diagnosa(id_kunjungan, _dx_entries)
        # Auto-fill tgl kontrol dari diagnosa primer bila dokter tidak mengisi manual
        if _tgl_kontrol is None and _primary_kontrol:
            from datetime import timedelta as _td
            _tgl_kontrol = _date.today() + _td(days=int(_primary_kontrol))

        _kj = db.get(_KjModel, id_kunjungan)
        if _kj is not None:
            _kj.tgl_kontrol_selanjutnya = _tgl_kontrol
            _kj.catatan_kontrol = _catatan_kontrol
            db.flush()
        FollowupService(db).generate_for_kunjungan(id_kunjungan, commit=False)
        db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse(url="/web/dokter/antrian", status_code=status.HTTP_303_SEE_OTHER)




# =============================================================================
# GET /web/dokter/soap/{id_kunjungan}/cetak - render Resume Medis SOAP
# =============================================================================
@router.get("/dokter/soap/{id_kunjungan}/cetak", response_class=HTMLResponse)
def dokter_cetak_soap(
    id_kunjungan: int,
    request: Request,
    db: DbSession,
    paper: str = "a5",
):
    """
    Render Resume Medis SOAP (A5/thermal) untuk dicetak browser.
    Audit log PRINT_SOAP ditulis di PrintService.
    Role: Dokter + Admin + Owner + Superadmin.
    """
    from app.services.print_service import PrintService

    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_dokter_antrian_role(user):
        return HTMLResponse(
            "<div style='padding:2rem'>403 - Hanya Dokter/Admin/Owner/Superadmin.</div>",
            status_code=403,
        )

    paper_normalized = (paper or "a5").lower().strip()
    if paper_normalized not in ("a5", "thermal"):
        paper_normalized = "a5"

    try:
        ctx = PrintService(db).prepare_soap_context(
            id_kunjungan=id_kunjungan,
            paper=paper_normalized,
            actor_id_staf=user.id_staf,
            request=request,
        )
    except HTTPException as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>{e.status_code} - Gagal Cetak Resume</h3>"
            f"<p>{e.detail}</p>"
            f"<a href='/web/dokter/antrian'>&larr; Kembali</a></div>",
            status_code=e.status_code,
        )
    except Exception as e:
        return HTMLResponse(
            f"<div style='padding:2rem;font-family:sans-serif'>"
            f"<h3>500 - Error</h3><p>{e!s}</p>"
            f"<a href='/web/dokter/antrian'>&larr; Kembali</a></div>",
            status_code=500,
        )

    template_name = (
        "print/soap_thermal.html"
        if paper_normalized == "thermal"
        else "print/soap_a5.html"
    )
    return templates.TemplateResponse(request, template_name, ctx)


# =============================================================================
# TODO-NEW-1 #29A — Alergi CRUD dokter access (inline di SOAP form)
# =============================================================================
def _dokter_can_edit_medrec(user) -> bool:
    """Permission: hanya Dokter / Admin / Owner / Superadmin."""
    role = (user.role.value if hasattr(user.role, "value") else str(user.role)).upper()
    return role in {"DOKTER", "ADMIN", "OWNER", "SUPERADMIN"}


@router.post("/dokter/kunjungan/{id_kunjungan}/alergi/tambah", response_class=HTMLResponse)
async def dokter_alergi_tambah(
    id_kunjungan: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403 — Hanya Dokter/Owner</div>", status_code=403)
    form = await request.form()
    id_pasien_str = form.get("id_pasien", "").strip()
    alergen = (form.get("alergen") or "").strip()
    gejala = (form.get("gejala") or "").strip()
    tingkat = (form.get("tingkat_keparahan") or "RINGAN").strip().upper()
    if not id_pasien_str.isdigit() or not alergen:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Data%20alergi%20tidak%20valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = AlergiAddRequest(
            id_pasien=int(id_pasien_str),
            alergen=alergen,
            gejala=gejala,
            tingkat_keparahan=TingkatKeparahanAlergiEnum[tingkat],  # name lookup (RINGAN/SEDANG/BERAT)
        )
        PasienService(db).tambah_alergi(payload, id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Alergi%20ditambahkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/dokter/kunjungan/{id_kunjungan}/alergi/{id_alergi}/ubah", response_class=HTMLResponse)
async def dokter_alergi_ubah(
    id_kunjungan: int, id_alergi: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    alergen = (form.get("alergen") or "").strip() or None
    gejala = form.get("gejala")  # allow empty string → clear
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
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Alergi%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/dokter/kunjungan/{id_kunjungan}/alergi/{id_alergi}/hapus", response_class=HTMLResponse)
def dokter_alergi_hapus(
    id_kunjungan: int, id_alergi: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        PasienService(db).hapus_alergi(
            id_alergi=id_alergi, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Alergi%20dihapus",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TODO-NEW-1 #29B - Penyakit Kronis CRUD dari SOAP form
# =============================================================================
@router.post("/dokter/kunjungan/{id_kunjungan}/penyakit-kronis/tambah", response_class=HTMLResponse)
async def dokter_penyakit_kronis_tambah(
    id_kunjungan: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    id_pasien_str = (form.get("id_pasien") or "").strip()
    nama = (form.get("nama_penyakit") or "").strip()
    catatan = (form.get("catatan") or "").strip()
    if not id_pasien_str.isdigit() or not nama:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Data%20tidak%20valid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        payload = PenyakitKronisAddRequest(
            id_pasien=int(id_pasien_str), nama_penyakit=nama, catatan=catatan,
        )
        PasienService(db).tambah_penyakit_kronis(payload, id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Penyakit%20kronis%20ditambahkan",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/dokter/kunjungan/{id_kunjungan}/penyakit-kronis/{id_penyakit}/ubah", response_class=HTMLResponse)
async def dokter_penyakit_kronis_ubah(
    id_kunjungan: int, id_penyakit: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
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
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Penyakit%20kronis%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/dokter/kunjungan/{id_kunjungan}/penyakit-kronis/{id_penyakit}/hapus", response_class=HTMLResponse)
def dokter_penyakit_kronis_hapus(
    id_kunjungan: int, id_penyakit: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    try:
        PasienService(db).hapus_penyakit_kronis(
            id_penyakit=id_penyakit, actor_id_staf=user.id_staf, request=request,
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Penyakit%20kronis%20dihapus",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# TODO-NEW-1 #29C - Antropometri edit dari SOAP form (dokter access)
# =============================================================================
@router.post("/dokter/kunjungan/{id_kunjungan}/antropometri/ubah", response_class=HTMLResponse)
async def dokter_antropometri_ubah(
    id_kunjungan: int, request: Request, db: DbSession,
):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
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
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?err=Gagal:%20{e!s}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/web/dokter/kunjungan/{id_kunjungan}/soap?ok=Antropometri%20diupdate",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# =============================================================================
# Penyakit Kronis — SET (checkbox dari master + Lain-lain). Reconcile via service.
# =============================================================================
@router.post("/dokter/kunjungan/{id_kunjungan}/penyakit-kronis/set", response_class=HTMLResponse)
async def dokter_penyakit_kronis_set(id_kunjungan: int, request: Request, db: DbSession):
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not _dokter_can_edit_medrec(user):
        return HTMLResponse("<div style='padding:2rem'>403</div>", status_code=403)
    form = await request.form()
    id_pasien_str = (form.get("id_pasien") or "").strip()
    nxt = (form.get("next") or f"/web/dokter/kunjungan/{id_kunjungan}/soap").strip()
    if not id_pasien_str.isdigit():
        return RedirectResponse(url=f"{nxt}?err=Data%20tidak%20valid", status_code=status.HTTP_303_SEE_OTHER)
    codes = []
    for k in form.getlist("kode"):
        try:
            codes.append(int(k))
        except (TypeError, ValueError):
            pass
    others = [t.strip() for t in form.getlist("lain_lain") if (t or "").strip()]
    try:
        PenyakitKronisService(db).set_state(int(id_pasien_str), codes, others, actor_id_staf=user.id_staf, request=request)
    except HTTPException as e:
        return RedirectResponse(url=f"{nxt}?err={e.detail}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url=f"{nxt}?err=Gagal:%20{e!s}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"{nxt}?ok=Penyakit%20kronis%20disimpan", status_code=status.HTTP_303_SEE_OTHER)
