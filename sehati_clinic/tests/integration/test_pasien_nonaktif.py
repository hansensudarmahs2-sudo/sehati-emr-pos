"""Audit mendalam tahap 1, T1-B (2026-10-13) — pasien NONAKTIF tak boleh mendapat
kunjungan/booking baru, dan penggabungan ikut memindahkan SALINAN tier.

Sebelum perbaikan (terbukti di DB dev): pasien VIP yang sudah DIGABUNG masih muncul di
dropdown booking, booking-nya diterima, check-in membuat kunjungan di ID duplikat
(riwayat terpecah lagi), sementara pasien yang bertahan ditolak booking ("REGULAR").
Keputusan dr. Hansen: salinan tier duplikat dikembalikan ke REGULAR.
Project_Memory/AUDIT_MENDALAM_2026-10-13.md.
"""
import random
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import MasterMembership, MasterStaf, Pasien, PasienMembershipHistory
from app.db.models._enums import GenderEnum, StafRoleEnum
from app.db.session import SessionLocal
from app.schemas.kunjungan import KunjunganLamaRequest
from app.schemas.pasien import PasienBaruRequest
from app.services.audit_pasien_service import AuditPasienService
from app.services.booking_service import BookingService
from app.services.kunjungan_service import KunjunganService
from app.services.pasien_service import PasienService


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _fo(db):
    s = MasterStaf(username=f"uji_t1b_{random.randint(10**6, 10**7)}",
                   password_hash=hash_password("x"), role=StafRoleEnum.FO,
                   nama_staf="Uji T1B", is_active=True)
    db.add(s); db.flush()
    return s


def _daftar(db, fo, tier="REGULAR"):
    r = PasienService(db).register_pasien_baru(
        PasienBaruRequest(nama=f"ZZ T1B {random.randint(10**6, 10**7)}",
                          jenis_kelamin=GenderEnum.PEREMPUAN),
        id_staf_fo=fo.id_staf, buat_kunjungan=False)
    p = db.get(Pasien, r["data"]["id_pasien"])
    p.tipe_membership = tier
    db.flush()
    return p


def _membership_aktif(db, p):
    m = db.execute(select(MasterMembership).limit(1)).scalar_one()
    db.add(PasienMembershipHistory(
        id_pasien=p.id_pasien, id_membership=m.id_membership, tgl_aktif=date.today(),
        tgl_expired=date.today() + timedelta(days=365), harga_bayar=0, is_active=True,
        status_aktivasi="ACTIVE"))
    db.flush()


def _gabung(db, fo, dup, srv):
    AuditPasienService(db).gabungkan(dup.id_pasien, srv.id_pasien, "uji T1B", fo.id_staf)


# ---------------------------------------------------------------- salinan tier
def test_gabung_memindahkan_tier_bila_duplikat_punya_membership_aktif(db):
    fo = _fo(db)
    dup, srv = _daftar(db, fo, "VIP"), _daftar(db, fo)
    _membership_aktif(db, dup)
    _gabung(db, fo, dup, srv)
    assert (dup.tipe_membership, srv.tipe_membership) == ("REGULAR", "VIP")


def test_gabung_tanpa_membership_aktif_tier_bertahan_tak_berubah(db):
    """Salinan VIP tanpa riwayat aktif (mis. kedaluwarsa) TIDAK boleh menaikkan tier
    pasien yang bertahan — tier mengikuti membership yang benar-benar pindah."""
    fo = _fo(db)
    dup, srv = _daftar(db, fo, "VIP"), _daftar(db, fo)
    _gabung(db, fo, dup, srv)
    assert (dup.tipe_membership, srv.tipe_membership) == ("REGULAR", "REGULAR")


# ---------------------------------------------------------------- booking
def test_duplikat_tak_muncul_di_dropdown_booking(db):
    fo = _fo(db)
    dup, srv = _daftar(db, fo, "VIP"), _daftar(db, fo)
    _gabung(db, fo, dup, srv)
    # Paksa salinan lama "VIP": penggabungan sudah mereset tier ke REGULAR, jadi tanpa
    # ini saringan is_active di dropdown tidak pernah benar-benar diuji (terbukti: suntikan
    # "dropdown tanpa saring" lolos sebelum baris ini ditambahkan). Pasien nonaktif
    # BUKAN hasil gabung (nonaktifkan biasa) juga mempertahankan tier-nya.
    dup.tipe_membership = "VIP"
    db.flush()
    assert dup.id_pasien not in [m["id_pasien"] for m in BookingService(db).list_members()]


def test_booking_untuk_duplikat_ditolak_dan_menunjuk_yang_bertahan(db):
    fo = _fo(db)
    dup, srv = _daftar(db, fo, "VIP"), _daftar(db, fo)
    nama_srv = srv.nama
    _gabung(db, fo, dup, srv)
    dup.tipe_membership = "VIP"      # paksa salinan lama: pagar is_active harus tetap menahan
    db.flush()
    with pytest.raises(HTTPException) as e:
        BookingService(db).create(dup.id_pasien, date.today(), "10:00", actor_id_staf=fo.id_staf)
    assert e.value.status_code == 409 and "NONAKTIF" in e.value.detail
    assert nama_srv in e.value.detail


def test_yang_bertahan_bisa_booking_sesudah_gabung(db):
    fo = _fo(db)
    dup, srv = _daftar(db, fo, "VIP"), _daftar(db, fo)
    _membership_aktif(db, dup)
    _gabung(db, fo, dup, srv)
    b = BookingService(db).create(srv.id_pasien, date.today(), "11:00", actor_id_staf=fo.id_staf)
    assert b.id_pasien == srv.id_pasien


# ---------------------------------------------------------------- kunjungan
def test_kunjungan_lama_untuk_pasien_nonaktif_ditolak(db):
    """Pagar di pembuat kunjungan menutup SEMUA pintu sekaligus: antrian Cari Pasien
    (termasuk lewat URL langsung), booking check-in, API v1."""
    fo = _fo(db)
    p = _daftar(db, fo)
    AuditPasienService(db).nonaktifkan(p.id_pasien, "uji", fo.id_staf)
    with pytest.raises(HTTPException) as e:
        KunjunganService(db).kunjungan_lama(
            KunjunganLamaRequest(id_pasien=p.id_pasien, status_antrian="ANTRI_KONSULTASI",
                                 keluhan_utama="", sumber_pendaftaran="WALK_IN",
                                 antropometri=None),
            id_staf_fo=fo.id_staf)
    assert e.value.status_code == 409 and "NONAKTIF" in e.value.detail


def test_beli_produk_untuk_pasien_nonaktif_ditolak(db):
    fo = _fo(db)
    p = _daftar(db, fo)
    AuditPasienService(db).nonaktifkan(p.id_pasien, "uji", fo.id_staf)
    with pytest.raises(HTTPException) as e:
        KunjunganService(db).beli_produk_lengkap(p.id_pasien, [], fo.id_staf)
    assert e.value.status_code == 409


def test_pita_nonaktif_di_halaman_detail():
    from app.web.routes._shared import templates
    src = templates.env.loader.get_source(templates.env, "pasien_detail.html")[0]
    assert "pasien.is_active == false" in src and "pasien_bertahan" in src
    from app.schemas.pasien import PasienResponse
    assert "is_active" in PasienResponse.model_fields   # tanpa ini pita tak pernah muncul
