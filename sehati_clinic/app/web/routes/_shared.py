"""
Shared utilities untuk semua web sub-routers.

Berisi:
- COOKIE_NAME, COOKIE_MAX_AGE_SECONDS — cookie config JWT
- templates — Jinja2Templates instance
- get_user_from_cookie() — auth helper dari cookie
- Role gates — STAF_MGMT, DOKTER_ANTRIAN, dll.
- Helper render context — build shell context (user + menu)

Pattern: sub-router lain import dari sini, supaya tidak duplikasi.
"""

from pathlib import Path

from fastapi import Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.config import settings
from app.core.security import JWTError, decode_access_token
from app.db.models import MasterStaf, StafRoleEnum
from app.web.menu import get_menu_for_role


# =============================================================================
# Cookie config
# =============================================================================
COOKIE_NAME = "sehati_session"
COOKIE_MAX_AGE_SECONDS = 21600  # 6 jam, match JWT
COOKIE_SECURE = settings.cookie_secure  # True (production HTTPS) / False (dev http)


# =============================================================================
# Templates — shared instance
# =============================================================================
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =============================================================================
# CSRF — Jinja2 helper untuk render hidden input di setiap form POST
# =============================================================================
def _csrf_input(request: Request) -> Markup:
    """
    Render hidden input dengan CSRF token dari request.state.

    Pakai di template:  {{ csrf_input(request) }}  di dalam <form>.
    Token di-set otomatis oleh CSRFMiddleware (app.core.csrf) saat GET request.
    """
    token = getattr(request.state, "csrf_token", "") if hasattr(request, "state") else ""
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


# Register sebagai Jinja2 global supaya bisa dipanggil dari template apapun
templates.env.globals["csrf_input"] = _csrf_input
templates.env.globals["idle_minutes"] = settings.session_idle_minutes
templates.env.globals["idle_warn_minutes"] = settings.session_idle_warn_minutes


# =============================================================================
# Role gates
# =============================================================================
STAF_MGMT_ROLES = {StafRoleEnum.OWNER, StafRoleEnum.SUPERADMIN, StafRoleEnum.ADMIN}

DOKTER_ANTRIAN_ROLES = {
    StafRoleEnum.DOKTER,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.ADMIN,
}

# Untuk: tambah/ubah/batal antrian via halaman search & antrian
ANTRIAN_MGMT_ROLES = {
    StafRoleEnum.FO,
    StafRoleEnum.ADMIN,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: akses halaman kasir (antrian bayar + tagihan + proses bayar)
KASIR_ROLES = {
    StafRoleEnum.KASIR,
    StafRoleEnum.ADMIN,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: akses halaman perawat (ruang tindakan)
PERAWAT_ROLES = {
    StafRoleEnum.PERAWAT,
    StafRoleEnum.DOKTER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: akses halaman apotek (antrian obat + serah + write-off + suggested order)
APOTEKER_ROLES = {
    StafRoleEnum.APOTEKER,
    StafRoleEnum.ADMIN,
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: akses Master Treatment + Master Produk (Owner + Superadmin only)
MASTER_DATA_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: akses Reports / Laporan (Owner + Superadmin + Admin)
REPORTS_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.ADMIN,
}

# Untuk: akses Owner Raw Data Export (C2) — Owner ONLY di MVP
# Defer Superadmin/Admin ke phase berikutnya
OWNER_ONLY_ROLES = {
    StafRoleEnum.OWNER,
}

# Untuk: Audit Integritas ID Pasien (#18 Lapis-2) — alat maintenance, bukan menu
# harian. Layarnya menampilkan data beberapa pasien BERDAMPINGAN untuk dibandingkan,
# jadi daftarnya sengaja sependek mungkin. Dibedakan dari OWNER_ONLY_ROLES (yang
# memang hanya Owner) dan dari MASTER_DATA_ROLES (kemampuan yang berbeda).
AUDIT_PASIEN_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Untuk: Export ke Finance sekarang (file-drop, DEC-066-R2) — Owner + Superadmin.
# Tombol manual/kontingensi; jalur normal tetap scheduler 05:00 WIB.
FINANCE_EXPORT_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# =============================================================================
# Pengadaan (PO + Receive + Stock Opname) — DEC-038
# =============================================================================
# Boleh CREATE PO + RECEIVE untuk semua tipe item (PRODUK + BAHAN)
PURCHASING_FULL_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.PURCHASING,
}

# Boleh CREATE PO + RECEIVE — APOTEKER hanya untuk PRODUK retail (filter di service)
PURCHASING_PRODUK_RETAIL_ROLES = PURCHASING_FULL_ROLES | {StafRoleEnum.APOTEKER}

# Boleh approve SUBMITTED→ORDERED dan Cancel PO
PURCHASING_APPROVE_CANCEL_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Boleh approve stock opname (apply selisih ke stok)
OPNAME_APPROVE_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
}

# Boleh view halaman Pengadaan (sub-set lihat sesuai filter UI)
PURCHASING_VIEW_ROLES = PURCHASING_PRODUK_RETAIL_ROLES


# =============================================================================
# Tier System (Decision C, 7 Juni 2026) — hierarchical authorization
# =============================================================================
# Owner       = Tier 0 (top, single per database, dibuat via SQL direct)
# Superadmin  = Tier 1 (semua kecuali Export Raw Data + Owner management)
# Admin       = Tier 2 (management operasional)
# Dokter/FO/Perawat/Kasir/Apoteker/Purchasing = Tier 3 (operasional)
#
# Prinsip: lower tier tidak bisa edit higher tier.
# Hard cap: maksimum 1 OWNER per database, creation hanya via SQL direct.
# Existing role sets (KASIR_ROLES, etc.) tetap jalan paralel — tier system
# ini layer guard tambahan khusus untuk role-change action di Master Staf.

TIER_OWNER = 0
TIER_SUPERADMIN = 1
TIER_ADMIN = 2
TIER_OPERATIONAL = 3

ROLE_TIERS: dict = {
    StafRoleEnum.OWNER: TIER_OWNER,
    StafRoleEnum.SUPERADMIN: TIER_SUPERADMIN,
    StafRoleEnum.ADMIN: TIER_ADMIN,
    StafRoleEnum.DOKTER: TIER_OPERATIONAL,
    StafRoleEnum.FO: TIER_OPERATIONAL,
    StafRoleEnum.PERAWAT: TIER_OPERATIONAL,
    StafRoleEnum.KASIR: TIER_OPERATIONAL,
    StafRoleEnum.APOTEKER: TIER_OPERATIONAL,
    StafRoleEnum.PURCHASING: TIER_OPERATIONAL,
}


def user_tier(user: MasterStaf) -> int:
    """Return tier numeric (0=Owner top, 3=Operasional bottom).
    Unknown role → 99 (deny by default).
    """
    return ROLE_TIERS.get(user.role, 99)


def can_edit_role_of(actor: MasterStaf, target: MasterStaf) -> bool:
    """True jika actor (lebih tinggi tier) bisa edit role target.
    Lower tier tidak boleh edit higher tier.
    Equal tier juga tidak boleh (kecuali edit diri sendiri,
    tapi self-edit-role tidak diizinkan di UI).
    """
    return user_tier(actor) < user_tier(target)


def can_promote_to_role(actor: MasterStaf, new_role) -> bool:
    """True jika actor bisa promote target ke new_role.
    Aturan:
    - Hanya OWNER yang bisa set OWNER role (special case).
    - Umum: actor tidak bisa promote ke tier lebih tinggi dari diri sendiri.
    """
    # Special case: OWNER role hanya boleh di-set oleh OWNER sendiri
    if new_role == StafRoleEnum.OWNER:
        return actor.role == StafRoleEnum.OWNER

    actor_tier_val = user_tier(actor)
    new_tier_val = ROLE_TIERS.get(new_role, 99)
    # actor bisa promote ke tier >= tier-nya sendiri (sama atau lebih rendah)
    return new_tier_val >= actor_tier_val


def require_staf_mgmt_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses /web/staf/*."""
    return user.role in STAF_MGMT_ROLES


def require_dokter_antrian_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses /web/dokter/*."""
    return user.role in DOKTER_ANTRIAN_ROLES


def require_antrian_mgmt_role(user: MasterStaf) -> bool:
    """True kalau user boleh tambah/ubah/batal antrian (FO/Admin/Owner/Superadmin)."""
    return user.role in ANTRIAN_MGMT_ROLES


def require_kasir_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses /web/kasir/* (Kasir/Admin/Owner/Superadmin)."""
    return user.role in KASIR_ROLES


def require_perawat_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses /web/ruang-tindakan/* (Perawat/Dokter/Admin/Owner)."""
    return user.role in PERAWAT_ROLES


def require_apoteker_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses /web/apotek/* (Apoteker/Admin/Owner/Superadmin)."""
    return user.role in APOTEKER_ROLES


def require_master_data_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses Master Treatment + Master Produk (Owner/Superadmin)."""
    return user.role in MASTER_DATA_ROLES


def require_reports_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses Reports / Laporan general (Owner/Superadmin/Admin)."""
    return user.role in REPORTS_ROLES


# REPORTS-COMPART (#324): per-role compartmentalized reports
# Dokter bisa akses Kinerja Dokter dengan auto-filter ke diri sendiri
KINERJA_DOKTER_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.ADMIN,
    StafRoleEnum.DOKTER,
}

# Kasir bisa akses Rekap Shift dengan auto-filter ke diri sendiri
REKAP_KASIR_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.ADMIN,
    StafRoleEnum.KASIR,
}


def require_kinerja_dokter_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses Kinerja Dokter report.
    Owner/Superadmin/Admin: lihat semua dokter.
    Dokter: lihat own data only (auto-filter di service layer).
    """
    return user.role in KINERJA_DOKTER_ROLES


def require_rekap_kasir_role(user: MasterStaf) -> bool:
    """True kalau user boleh akses Rekap Kasir Shift report.
    Owner/Superadmin/Admin: lihat semua kasir.
    Kasir: lihat own shift only (auto-filter di service layer).
    """
    return user.role in REKAP_KASIR_ROLES


def is_dokter_role(user: MasterStaf) -> bool:
    """True kalau role tepat DOKTER (untuk decide auto-filter)."""
    return user.role == StafRoleEnum.DOKTER


def is_kasir_role(user: MasterStaf) -> bool:
    """True kalau role tepat KASIR (untuk decide auto-filter)."""
    return user.role == StafRoleEnum.KASIR


def is_perawat_role(user: MasterStaf) -> bool:
    """True kalau role tepat PERAWAT (untuk decide auto-filter komisi)."""
    return user.role == StafRoleEnum.PERAWAT


def require_owner_only(user: MasterStaf) -> bool:
    """True kalau user adalah Owner (untuk Owner Raw Data Export — C2)."""
    return user.role in OWNER_ONLY_ROLES


def require_audit_pasien_role(user: MasterStaf) -> bool:
    """True kalau user boleh membuka Audit Integritas ID Pasien (Owner/Superadmin)."""
    return user.role in AUDIT_PASIEN_ROLES


def require_finance_export_role(user: MasterStaf) -> bool:
    """True kalau user boleh Export ke Finance sekarang (Owner/Superadmin)."""
    return user.role in FINANCE_EXPORT_ROLES


def require_purchasing_full_role(user: MasterStaf) -> bool:
    """True kalau user boleh PO untuk SEMUA tipe item (Owner/Superadmin/Purchasing)."""
    return user.role in PURCHASING_FULL_ROLES


def require_purchasing_view_role(user: MasterStaf) -> bool:
    """True kalau user boleh view halaman Pengadaan (termasuk Apoteker untuk filter retail)."""
    return user.role in PURCHASING_VIEW_ROLES


def require_purchasing_approve_cancel_role(user: MasterStaf) -> bool:
    """True kalau user boleh approve SUBMITTED→ORDERED dan cancel PO (Owner/Superadmin)."""
    return user.role in PURCHASING_APPROVE_CANCEL_ROLES


def require_opname_approve_role(user: MasterStaf) -> bool:
    """True kalau user boleh approve stock opname (Owner/Superadmin)."""
    return user.role in OPNAME_APPROVE_ROLES


def user_can_purchase_bahan(user: MasterStaf) -> bool:
    """
    True kalau user boleh PO item tipe BAHAN.
    Apoteker → False (cuma boleh produk retail).
    """
    return user.role in PURCHASING_FULL_ROLES


def user_can_purchase_produk_cabin_alat(user: MasterStaf) -> bool:
    """
    True kalau user boleh PO produk dengan tipe CABIN/ALAT.
    Apoteker → False (hanya RETAIL).
    """
    return user.role in PURCHASING_FULL_ROLES


# =============================================================================
# FO-ASSIGN-DOKTER helper (Task #329)
# =============================================================================
def get_dokter_aktif_list(db) -> list[MasterStaf]:
    """
    Return list staf aktif dengan role DOKTER saja, sorted by nama.
    Dipakai untuk dropdown 'Dokter dituju' di FO entry points.
    OWNER tidak di-include — Owner punya peran management, bukan klinis.
    """
    from sqlalchemy import select

    stmt = (
        select(MasterStaf)
        .where(
            MasterStaf.is_active == True,  # noqa: E712
            MasterStaf.role == StafRoleEnum.DOKTER,
        )
        .order_by(MasterStaf.nama_staf.asc())
    )
    return list(db.execute(stmt).scalars().all())


# =============================================================================
# Auth helper — read user dari cookie JWT
# =============================================================================
def get_user_from_cookie(request: Request, db) -> MasterStaf | None:
    """
    Read JWT dari cookie, decode, return MasterStaf. None kalau invalid.

    Defensive: catch JWTError + ValueError/TypeError supaya cookie payload
    yang aneh (mis. sub bukan integer) tidak crash 500, tapi return None
    (treat as not authenticated).
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        id_staf_raw = payload.get("sub")
        if id_staf_raw is None:
            return None
        id_staf = int(id_staf_raw)
    except (JWTError, ValueError, TypeError):
        return None

    staf = db.get(MasterStaf, id_staf)
    if staf is None or not staf.is_active or not staf.is_logged_in:
        return None
    return staf


# =============================================================================
# A8 (audit P2-3/P2-5): guard auth bersama + bentuk 403/401 STANDAR
# Kurangi boilerplate + samakan bentuk respons. Route baru WAJIB pakai ini;
# route lama migrasi bertahap.
# =============================================================================
LOGIN_URL = "/web/login"


def login_redirect() -> RedirectResponse:
    """User belum login → 303 redirect ke /web/login (standar)."""
    return RedirectResponse(url=LOGIN_URL, status_code=status.HTTP_303_SEE_OTHER)


def forbidden(detail: str = "Anda tidak punya akses ke halaman ini.", *, partial: bool = False) -> HTMLResponse:
    """403 standar. partial=True → fragment kecil (target HTMX); else kartu full-page."""
    if partial:
        html = f"<div class='p-4 bg-red-50 text-red-700 rounded-lg text-sm'>⚠ {detail}</div>"
    else:
        html = (
            "<div style='max-width:32rem;margin:3rem auto;padding:2rem;border:1px solid #fecaca;"
            "background:#fef2f2;border-radius:.75rem;color:#b91c1c;font-family:system-ui'>"
            "<div style='font-weight:600;margin-bottom:.5rem'>403 — Akses ditolak</div>"
            f"<div style='font-size:.875rem'>{detail}</div>"
            "<div style='margin-top:1rem'><a href='/web/dashboard' style='color:#2563eb'>← Kembali ke Dashboard</a></div>"
            "</div>"
        )
    return HTMLResponse(html, status_code=status.HTTP_403_FORBIDDEN)


def session_expired(*, partial: bool = False) -> HTMLResponse:
    """401 standar (sesi habis) untuk target HTMX; frontend bisa redirect."""
    if partial:
        html = "<div class='p-4 bg-amber-50 text-amber-700 rounded-lg text-sm'>Sesi habis. Silakan login ulang.</div>"
    else:
        html = "<div style='padding:2rem'>Sesi habis. <a href='/web/login'>Login ulang</a>.</div>"
    return HTMLResponse(html, status_code=status.HTTP_401_UNAUTHORIZED)


def web_guard(request: Request, db, role_check=None, *, partial: bool = False):
    """Guard bersama. Return (user, None) kalau lolos; (None, response) kalau harus stop.

    Contoh:
        user, resp = web_guard(request, db, require_kasir_role)
        if resp:
            return resp
    role_check = None → cukup butuh login (tanpa cek role).
    """
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, login_redirect()
    if role_check is not None and not role_check(user):
        return None, forbidden(partial=partial)
    return user, None


# Label field Indonesia untuk pesan validasi ramah
_VALIDATION_FIELD_LABEL = {
    "username": "Username", "password": "Password", "nama_staf": "Nama",
    "pin": "PIN", "role": "Role", "new_password": "Password baru",
    "old_password": "Password lama",
}


def friendly_validation_error(exc) -> str:
    """Ubah pydantic ValidationError → pesan Indonesia ringkas (tanpa URL/type teknis)."""
    try:
        errors = exc.errors()
    except Exception:
        return "Data tidak valid."
    msgs = []
    for err in errors:
        loc = err.get("loc", ())
        field = loc[-1] if loc else ""
        label = _VALIDATION_FIELD_LABEL.get(field, str(field).replace("_", " ").capitalize())
        etype = err.get("type", "")
        c = err.get("ctx", {}) or {}
        if etype == "string_too_short":
            msgs.append(f"{label} minimal {c.get('min_length', '?')} karakter.")
        elif etype == "string_too_long":
            msgs.append(f"{label} maksimal {c.get('max_length', '?')} karakter.")
        elif etype == "string_pattern_mismatch":
            msgs.append(f"{label} hanya boleh huruf, angka, dan garis bawah (_).")
        elif etype == "missing":
            msgs.append(f"{label} wajib diisi.")
        else:
            msgs.append(f"{label} tidak valid.")
    return " ".join(dict.fromkeys(msgs)) if msgs else "Data tidak valid."


# =============================================================================
# Render helpers — shell context untuk template
# =============================================================================
def script_json(obj) -> str:
    """JSON aman untuk ditanam di <script type="application/json">...</script>.

    P1-4 (AUDIT_SEHATI_2026-07-10): `json.dumps` biasa tak meng-escape '<' '>' '&',
    jadi nilai master-data (nama produk/lot) seperti '</script>...' bisa keluar dari
    blok script → stored XSS. Helper ini escape pemicu breakout ke bentuk \\uXXXX
    (tetap JSON valid). Dipakai bareng `| safe` di template (string sudah aman).
    """
    import json as _json

    s = _json.dumps(obj, ensure_ascii=False, default=str)
    return (
        s.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def role_value_of(user: MasterStaf) -> str:
    """Return string value of user.role (handle enum & string)."""
    return user.role.value if hasattr(user.role, "value") else str(user.role)


APP_NAME = "Sehati"  # Nama aplikasi eMR + POS. Bukan nama klinik.
DEFAULT_KLINIK_NAMA = "Klinik Anda"  # Placeholder bila klinik_config belum diisi



def get_klinik_nama_safe(db=None) -> str:
    """Ambil nama klinik dari master_klinik_config. Fallback ke default."""
    if db is None:
        return DEFAULT_KLINIK_NAMA
    try:
        from app.db.models import MasterKlinikConfig
        cfg = db.get(MasterKlinikConfig, 1)
        if cfg and cfg.nama_klinik:
            return cfg.nama_klinik
    except Exception as e:
        # Fallback ke default — jangan crash kalau DB lookup gagal
        import logging
        logging.getLogger(__name__).warning(
            "Gagal fetch nama_klinik dari MasterKlinikConfig: %s — fallback ke default",
            e,
        )
    return DEFAULT_KLINIK_NAMA


def build_shell_context(user: MasterStaf, db=None, current_path: str = "", **extra) -> dict:
    """Build context dict untuk shell template (sidebar + topbar + page body).

    Wajib pass user (cek role untuk menu). db optional — kalau ada, fetch
    nama klinik dari master_klinik_config. Extra kwargs ditambah ke ctx.
    """
    from app.web.menu import get_menu_for_role, is_active

    role_str = role_value_of(user)
    menu_groups = get_menu_for_role(role_str)

    ctx = {
        "user": user,
        "current_path": current_path,
        "menu_groups": menu_groups,
        "active_url_check": is_active,
        "page_subtitle": "",
    }
    # Inject klinik config kalau db dipass — untuk branding di sidebar/topbar
    cfg = None
    if db is not None:
        try:
            from app.services.klinik_config_service import KlinikConfigService
            cfg = KlinikConfigService(db).get_config()
        except Exception:
            cfg = None
    ctx["klinik_config"] = cfg
    # FIX: dulu klinik_nama TIDAK di-set di shell → topbar kosong di banyak halaman.
    # Sekarang selalu diisi (dari config / fallback default).
    ctx["klinik_nama"] = (getattr(cfg, "nama_klinik", None) or DEFAULT_KLINIK_NAMA)
    ctx["klinik_logo_path"] = getattr(cfg, "logo_path", None)
    ctx["klinik_mini_logo_path"] = getattr(cfg, "mini_logo_path", None)  # #43; None sampai kolom ada
    # #5 Badge notifikasi per role — 1 query grouped count (cached ~10s, clinic-wide).
    badge_counts = {}
    if db is not None:
        try:
            from app.core import ttl_cache as _tc

            def _bc():
                from datetime import date as _date
                from sqlalchemy import func as _f, select as _sel
                from app.db.models import Kunjungan as _K
                rows = db.execute(
                    _sel(_K.status_antrian, _f.count())
                    .where(
                        _f.date(_K.tgl_kunjungan) == _date.today(),
                        _K.status_antrian.in_(["ANTRI_KONSULTASI", "ANTRI_TREATMENT", "ANTRI_BAYAR", "ANTRI_OBAT"]),
                    )
                    .group_by(_K.status_antrian)
                ).all()
                return {s: int(c) for s, c in rows}

            badge_counts = _tc.get_or_set("badge:antrian", 10.0, _bc)
        except Exception:
            badge_counts = {}
    # Draf SOAP dari apotek yang menunggu persetujuan (2026-09-25).
    # WAJIB disalin dulu: `badge_counts` datang dari cache BERSAMA antar pengguna,
    # sedangkan angka ini PER DOKTER. Menambahkan langsung ke objek cache akan
    # membocorkan hitungan dokter A ke dokter B.
    badge_counts = dict(badge_counts or {})
    if db is not None and user is not None:
        try:
            from sqlalchemy import func as _f2, select as _sel2
            from app.db.models import (
                Kunjungan as _K2, PemeriksaanKlinis as _PK2, StafRoleEnum as _Role2,
            )
            _q = (
                _sel2(_f2.count(_PK2.id_pemeriksaan))
                .join(_K2, _K2.id_kunjungan == _PK2.id_kunjungan)
                .where(_PK2.status_soap == "DRAFT_APOTEK")
            )
            # Dokter melihat miliknya; Owner/Admin melihat seluruh antrian supaya
            # tumpukan yang tak tergarap tidak tersembunyi di akun orang lain.
            if user.role == _Role2.DOKTER:
                _q = _q.where(_K2.id_staf_dokter_assigned == user.id_staf)
            _n = db.execute(_q).scalar() or 0
            if _n:
                badge_counts["DRAF_SOAP"] = int(_n)
        except Exception:
            pass
    ctx["badge_counts"] = badge_counts
    # Obat Tertunda (P1-1): hitung untuk kartu dashboard + ikon notifikasi header.
    obat_tertunda = {"total": 0, "overdue": 0}
    if db is not None:
        try:
            from app.core import ttl_cache as _tc

            def _ot():
                from datetime import date as _date
                from sqlalchemy import select as _sel
                from app.db.models import Kunjungan as _K
                today = _date.today()
                rows = _db_ot = db.execute(
                    _sel(_K.tgl_janji_kirim).where(
                        _K.status_antrian == "COMPLETED",
                        _K.tgl_janji_kirim.is_not(None),
                    )
                ).all()
                tot = len(rows)
                od = sum(1 for (d,) in rows if d is not None and d <= today)
                return {"total": tot, "overdue": od}

            obat_tertunda = _tc.get_or_set("obat:tertunda", 30.0, _ot)
        except Exception:
            obat_tertunda = {"total": 0, "overdue": 0}
    ctx["obat_tertunda"] = obat_tertunda
    ctx["can_obat_tertunda"] = role_str in {"Owner", "Superadmin", "Admin", "Kasir", "FO", "Apoteker"}
    # M4: Membership menunggu aktivasi (PAID) — kartu dashboard + badge header.
    membership_aktivasi = {"total": 0}
    if db is not None:
        try:
            from app.core import ttl_cache as _tc

            def _ma():
                from app.services.membership_service import MembershipService as _MS
                return {"total": _MS(db).count_awaiting_activation()}

            membership_aktivasi = _tc.get_or_set("membership:aktivasi", 30.0, _ma)
        except Exception:
            membership_aktivasi = {"total": 0}
    ctx["membership_aktivasi"] = membership_aktivasi
    ctx["can_membership_aktivasi"] = role_str in {"Owner", "Superadmin", "Admin", "Kasir", "FO"}
    ctx.update(extra)
    return ctx


def render_cached(cache_key: str, ttl: float, producer):
    """Cache BYTES fragment hasil render (TAMPILAN saja).

    REGULASI (KESTABILAN_OPERASIONAL_EMRPOS §9): auth/role WAJIB dicek SEBELUM ini
    (jangan pernah cache keputusan auth). `producer()` -> Response ber-.body
    (mis. TemplateResponse). Bytes immutable → tak ada risiko shared-mutation.
    Kill-switch: app.core.ttl_cache.set_enabled(False) mematikan seketika.
    """
    from app.core import ttl_cache

    def _bytes():
        resp = producer()
        return bytes(getattr(resp, "body", b"") or b"")

    return HTMLResponse(content=ttl_cache.get_or_set(cache_key, ttl, _bytes))


__all__ = [
    "COOKIE_NAME",
    "templates",
    "STAF_MGMT_ROLES", "DOKTER_ANTRIAN_ROLES", "ANTRIAN_MGMT_ROLES",
    "KASIR_ROLES", "PERAWAT_ROLES", "APOTEKER_ROLES",
    "MASTER_DATA_ROLES", "REPORTS_ROLES", "OWNER_ONLY_ROLES",
    "FINANCE_EXPORT_ROLES", "require_finance_export_role",
    "KINERJA_DOKTER_ROLES", "REKAP_KASIR_ROLES",
    "PURCHASING_FULL_ROLES", "PURCHASING_PRODUK_RETAIL_ROLES",
    "PURCHASING_APPROVE_CANCEL_ROLES", "OPNAME_APPROVE_ROLES",
    "TIER_OWNER", "TIER_SUPERADMIN", "TIER_ADMIN", "TIER_OPERATIONAL",
    "ROLE_TIERS", "user_tier", "can_edit_role_of", "can_promote_to_role",
    "require_staf_mgmt_role", "require_dokter_antrian_role",
    "require_antrian_mgmt_role", "require_kasir_role", "require_perawat_role",
    "require_apoteker_role", "require_master_data_role", "require_reports_role",
    "require_owner_only", "require_audit_pasien_role",
    "require_kinerja_dokter_role", "require_rekap_kasir_role",
    "is_dokter_role", "is_perawat_role", "is_kasir_role",
    "require_purchasing_full_role", "require_purchasing_view_role",
    "require_purchasing_approve_cancel_role", "require_opname_approve_role",
    "user_can_purchase_bahan", "user_can_purchase_produk_cabin_alat",
    "DEFAULT_KLINIK_NAMA", "get_klinik_nama_safe",
    "build_shell_context", "get_user_from_cookie",
    "login_redirect", "forbidden", "session_expired", "web_guard", "LOGIN_URL",
    "friendly_validation_error",
    "get_dokter_aktif_list",
    "render_cached",
    "script_json",
]
