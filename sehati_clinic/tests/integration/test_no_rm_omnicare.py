"""No. RM Omnicare (sistem lama) — dr. Hansen 2026-10-07.

Sehati menjadi SUMBER nomor RM Omnicare selama input ganda: staf membaca nomor tertinggi
di Cari Pasien, mendaftarkan pasien dengan nomor berikutnya, lalu menyalin datanya ke
Omnicare lewat halaman /web/pasien/{id}/omnicare. Yang dijaga di sini:

- bentuk baku (JJ-/JC- + angka, tanpa nol depan) — nomor sama diketik dua gaya tidak
  boleh lolos dari unique index;
- "tertinggi" dibandingkan sebagai ANGKA (teks: "JJ-99999" > "JJ-900001");
- satu nomor = satu pasien, termasuk pasien NONAKTIF (nomornya dipensiunkan);
- edit: "" menghapus, None tidak mengubah;
- penggabungan memindahkan nomor; dua nomor berbeda menolak penggabungan;
- nomor ini TIDAK boleh keluar lewat paket klinis.

Setiap test memakai sesi yang di-rollback (commit = flush).
"""
import random

import pytest
from fastapi import HTTPException

from app.core.no_rm_omnicare import (
    NoRmOmnicareTidakSah, gabung_isian, normalisasi_no_rm_omnicare,
)
from app.db.models import MasterStaf, Pasien
from app.db.models._enums import GenderEnum, StafRoleEnum
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.schemas.pasien import PasienBaruRequest, PasienUpdateRequest
from app.services.audit_pasien_service import AuditPasienService
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
    s = MasterStaf(username=f"uji_omni_{random.randint(10**6, 10**7)}",
                   password_hash=hash_password("x"), role=StafRoleEnum.FO,
                   nama_staf="Uji Omnicare FO", is_active=True)
    db.add(s); db.flush()
    return s


def _daftar(db, staf, omni="", nama=None):
    nama = nama or f"Uji Omni {random.randint(10**6, 10**7)}"
    hasil = PasienService(db).register_pasien_baru(
        PasienBaruRequest(nama=nama, jenis_kelamin=GenderEnum.PEREMPUAN, no_rm_omnicare=omni),
        id_staf_fo=staf.id_staf, buat_kunjungan=False)
    return db.get(Pasien, hasil["data"]["id_pasien"])


# ---------------------------------------------------------------- bentuk
@pytest.mark.parametrize("raw, baku", [
    ("JJ-8123", "JJ-8123"), (" jj-8123 ", "JJ-8123"), ("JJ-08123", "JJ-8123"),
    ("jc 2010", "JC-2010"), ("JJ10234", "JJ-10234"), ("", None), ("-", None), (None, None),
])
def test_bentuk_baku(raw, baku):
    assert normalisasi_no_rm_omnicare(raw) == baku


@pytest.mark.parametrize("raw", ["JX-8123", "8123", "JJ-81A3", "RM-8123", "JJ-0"])
def test_bentuk_salah_ditolak(raw):
    with pytest.raises(NoRmOmnicareTidakSah):
        normalisasi_no_rm_omnicare(raw)


# ---------------------------------------------------------------- isian form
# Tombol cabang + kotak angka (dr. Hansen 2026-10-07): prefix otomatis, staf hanya
# mengetik angka. Hasilnya lalu melewati normalisasi yang sama.
@pytest.mark.parametrize("cabang, angka, baku", [
    ("JJ", "8124", "JJ-8124"),
    ("JC", "2010", "JC-2010"),
    (None, "8124", "JJ-8124"),          # default Jemur
    ("JJ", "08124", "JJ-8124"),         # nol depan tetap dibakukan
    ("JJ", "JC-2010", "JC-2010"),       # nomor LENGKAP ditempel: prefix eksplisit menang
    ("JC", "", None),                   # angka kosong = tidak ada / hapus
])
def test_isian_cabang_dan_angka(cabang, angka, baku):
    assert normalisasi_no_rm_omnicare(gabung_isian(cabang, angka)) == baku


@pytest.mark.parametrize("cabang, angka", [("JX", "8124"), ("JJ", "81-24x")])
def test_isian_salah_ditolak(cabang, angka):
    with pytest.raises(NoRmOmnicareTidakSah):
        normalisasi_no_rm_omnicare(gabung_isian(cabang, angka))


# ---------------------------------------------------------------- tertinggi
def test_tertinggi_dibanding_sebagai_angka_bukan_teks(db):
    """Sebagai teks "JJ-99999" > "JJ-900001". Tepat saat nomor bertambah digit,
    perbandingan teks menunjuk nomor yang salah → staf membagikan nomor ganda."""
    fo = _fo(db)
    _daftar(db, fo, "JJ-99999")
    _daftar(db, fo, "JJ-900001")
    _daftar(db, fo, "JC-900002")
    t = PasienService(db).rm_omnicare_tertinggi()
    assert t["JJ"] == "JJ-900001" and t["JC"] == "JC-900002"


# ---------------------------------------------------------------- daftar baru
def test_daftar_dengan_nomor_tersimpan_baku(db):
    p = _daftar(db, _fo(db), " jj-0900011 ")
    assert p.no_rm_omnicare == "JJ-900011"


def test_nomor_ganda_ditolak_termasuk_gaya_ketik_lain(db):
    fo = _fo(db)
    pemilik = _daftar(db, fo, "JJ-900021")
    with pytest.raises(HTTPException) as e:
        _daftar(db, fo, "JJ-0900021")          # angka sama, diketik dengan nol depan
    assert e.value.status_code == 409 and pemilik.nama in e.value.detail


def test_bentuk_salah_ditolak_saat_daftar(db):
    with pytest.raises(HTTPException) as e:
        _daftar(db, _fo(db), "JX-1")
    assert e.value.status_code == 400 and "JJ-" in e.value.detail


def test_tanpa_nomor_boleh_banyak_pasien(db):
    fo = _fo(db)
    assert _daftar(db, fo).no_rm_omnicare is None
    assert _daftar(db, fo).no_rm_omnicare is None   # NULL, bukan "" — unique tak bentrok


# ---------------------------------------------------------------- edit
def test_edit_isi_lalu_hapus_none_tidak_mengubah(db):
    fo = _fo(db)
    p = _daftar(db, fo)
    svc = PasienService(db)
    svc.update_pasien_profile(p.id_pasien, PasienUpdateRequest(no_rm_omnicare="jc-900031"), fo.id_staf)
    assert p.no_rm_omnicare == "JC-900031"
    svc.update_pasien_profile(p.id_pasien, PasienUpdateRequest(nama=p.nama + " X"), fo.id_staf)
    assert p.no_rm_omnicare == "JC-900031"                     # None = tidak diubah
    svc.update_pasien_profile(p.id_pasien, PasienUpdateRequest(no_rm_omnicare=""), fo.id_staf)
    assert p.no_rm_omnicare is None                            # "" = hapus


def test_edit_ke_nomor_pasien_nonaktif_ditolak(db):
    """Pasien nonaktif TETAP memegang nomornya (dipensiunkan) — kalau dilepas, nomor
    tertinggi bisa turun dan nomor yang sudah dipakai di Omnicare dibagikan lagi."""
    fo = _fo(db)
    lama = _daftar(db, fo, "JJ-900041")
    AuditPasienService(db).nonaktifkan(lama.id_pasien, "uji duplikat", fo.id_staf)
    assert lama.no_rm_omnicare == "JJ-900041"
    baru = _daftar(db, fo)
    with pytest.raises(HTTPException) as e:
        PasienService(db).update_pasien_profile(
            baru.id_pasien, PasienUpdateRequest(no_rm_omnicare="JJ-900041"), fo.id_staf)
    assert e.value.status_code == 409 and "NONAKTIF" in e.value.detail


# Terpisah: penolakan di service me-ROLLBACK, dan di test (commit=flush) rollback itu
# ikut membuang data uji — pemeriksaan sesudahnya butuh setup sendiri.
def test_tertinggi_ikut_menghitung_pasien_nonaktif(db):
    fo = _fo(db)
    lama = _daftar(db, fo, "JJ-900991")
    AuditPasienService(db).nonaktifkan(lama.id_pasien, "uji duplikat", fo.id_staf)
    assert PasienService(db).rm_omnicare_tertinggi()["JJ"] == "JJ-900991"


# ---------------------------------------------------------------- cari & terbaru
def test_cari_dengan_gaya_ketik_lain(db):
    p = _daftar(db, _fo(db), "JJ-900051")
    ids = [r.id_pasien for r in PasienService(db).search("jj-0900051")]
    assert p.id_pasien in ids


def test_terbaru_urut_pendaftaran_tanpa_pasien_nonaktif(db):
    fo = _fo(db)
    a = _daftar(db, fo, "JJ-900061")
    b = _daftar(db, fo)
    AuditPasienService(db).nonaktifkan(b.id_pasien, "uji", fo.id_staf)
    c = _daftar(db, fo)
    ids = [r.id_pasien for r in PasienService(db).terbaru(10)]
    assert ids[:2] == [c.id_pasien, a.id_pasien] and b.id_pasien not in ids


# ---------------------------------------------------------------- gabung
def test_gabung_memindahkan_nomor_ke_yang_bertahan(db):
    fo = _fo(db)
    dup = _daftar(db, fo, "JJ-900071")
    srv = _daftar(db, fo)
    hasil = AuditPasienService(db).gabungkan(dup.id_pasien, srv.id_pasien, "uji", fo.id_staf)
    assert srv.no_rm_omnicare == "JJ-900071" and dup.no_rm_omnicare is None
    assert "JJ-900071" in hasil["message"]


def test_gabung_ditolak_bila_keduanya_punya_nomor(db):
    fo = _fo(db)
    dup = _daftar(db, fo, "JJ-900081")
    srv = _daftar(db, fo, "JJ-900082")
    pra = AuditPasienService(db).pratinjau_gabung(dup.id_pasien, srv.id_pasien)
    assert not pra["bisa_digabung"]
    assert any("Omnicare" in h for h in pra["penghalang"])


# ---------------------------------------------------------------- ekspor
def test_nomor_omnicare_terlarang_di_paket_klinis():
    from app.services.clinical_export_service import KOLOM_TERLARANG
    assert "no_rm_omnicare" in KOLOM_TERLARANG
