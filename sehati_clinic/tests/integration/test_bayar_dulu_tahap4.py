"""Bayar dulu tahap 4 (2026-10-28) — Project_Memory/RENCANA_BAYAR_DULU_TAHAP4.md.

T4-1 Simpan sebagai hak: tindakan PENDING yang SUDAH dibayar (di muka) lalu ditolak pasien.
Dulu satu-satunya jawaban adalah 400 "tunggu tahap 4" — tindakan menggantung PENDING,
kunjungan tak pernah COMPLETED, tutup kasir terhalang selamanya.

Tiga bentuk, menurut cara tindakan itu dibayar (sama dengan `_compute_charge`):
- berharga (harga treatment)  → BATAL + hak PRABAYAR baru (6 bulan dari tanggal bayar);
- kuota member (Rp 0)         → BATAL + kuota dikembalikan (P1);
- sesi series (sesi 1 paket / sesi 2..N Rp 0) → BATAL + sesi kembali PENDING (P1/P2).
"""
from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import AuditLog, KunjunganTindakan, PasienRencanaTreatment
from tests.integration.test_audit_tahap2 import (V, _siapkan, _bayar, _resep,  # noqa: F401
                                                 _trx_terakhir, _rencana, db)
from tests.integration.test_bayar_dulu_tahap1 import _soap, _tindakan_baru, _kuota_pending, _serah

ALASAN = "pasien berubah pikiran"


def _hak(db, t, staf, alasan=ALASAN):
    from app.services.treatment_service import TreatmentService
    return TreatmentService(db).simpan_sebagai_hak(t.id_kunjungan_tindakan, alasan, staf.id_staf)


def _prabayar_dari(db, t):
    return db.execute(select(PasienRencanaTreatment).where(
        PasienRencanaTreatment.sumber_rencana == "PRABAYAR",
        PasienRencanaTreatment.id_referensi_sumber == t.id_kunjungan_tindakan)).scalars().all()


def _dibayar_di_muka(db, status="PENDING"):
    """Konsul + satu tindakan berharga, dibayar bersama (di muka)."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, status)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    assert t.id_transaksi is not None
    return staf, k, t


# ---------------------------------------------------------------- T4-1
def test_tindakan_berharga_jadi_hak_prabayar(db):
    from app.services.kasir_closing_service import KasirClosingService
    from app.services.treatment_service import tambah_bulan
    staf, k, t = _dibayar_di_muka(db)
    trx = _trx_terakhir(db, k)
    assert V(k.status_antrian) == "ANTRI_TREATMENT"
    sebelum = KasirClosingService(db)._pending_antrian_hari_ini().get("ANTRI_TREATMENT", 0)
    hasil = _hak(db, t, staf)                         # dulu: tak ada jalan (400 di Batalkan)
    db.refresh(t); db.refresh(k)
    assert V(t.status_tindakan) == "BATAL"
    assert t.id_transaksi == trx.id_transaksi         # pembayarnya tetap tercatat
    hak = _prabayar_dari(db, t)
    assert len(hak) == 1
    h = hak[0]
    assert (V(h.status), h.urutan_sesi, h.id_kunjungan_pembuat) == ("PENDING", 1, None)
    assert (h.id_pasien, h.id_treatment) == (k.id_pasien, t.id_treatment)
    assert h.tgl_target_akhir == tambah_bulan(trx.waktu_bayar.date(), 6)
    assert h.nama_tindakan
    assert V(k.status_antrian) == "COMPLETED"
    assert hasil["data"]["bentuk"] == "HAK" and hasil["data"]["id_rencana"] == h.id_rencana
    sesudah = KasirClosingService(db)._pending_antrian_hari_ini().get("ANTRI_TREATMENT", 0)
    assert sesudah == sebelum - 1                     # tutup kasir tak lagi terhalang
    log = db.execute(select(AuditLog).where(AuditLog.aksi == "TINDAKAN_JADI_HAK",
                                            AuditLog.id_target == t.id_kunjungan_tindakan)).scalar_one()
    assert ALASAN in str(log.data_baru) and str(h.id_rencana) in str(log.data_baru)


def test_hak_tidak_ikut_tagihan_lagi(db):
    """Tindakan BATAL tidak ditagih ulang dan tidak membuat tagihan susulan."""
    from app.services.kasir_service import KasirService
    staf, k, t = _dibayar_di_muka(db)
    _hak(db, t, staf)
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    assert tagihan.sudah_lunas is True
    assert t.id_kunjungan_tindakan not in [r.id_kunjungan_tindakan for r in tagihan.rincian_tindakan]


def test_kunjungan_dengan_sisa_lain_tidak_completed(db):
    """Hak atas satu tindakan; tindakan lain yang dibayar masih menunggu → tetap di perawat."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t1 = _tindakan_baru(db, k, "PENDING")
    t2 = _tindakan_baru(db, k, "PENDING")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t1)
    _hak(db, t1, staf)
    db.refresh(k); db.refresh(t2)
    assert V(t2.status_tindakan) == "PENDING"
    assert V(k.status_antrian) == "ANTRI_TREATMENT"


def test_kuota_prabayar_jadi_hak_mengembalikan_kuota_sekali(db):
    """P1: tindakan kuota (Rp 0) → kuota kembali, BUKAN hak PRABAYAR baru (kuota sudah hak
    dengan batasnya sendiri). Batal kunjungan sesudahnya tidak mengembalikannya lagi."""
    from app.services._batal_tindakan import bereskan_kunjungan
    from app.services.audit_service import AuditService
    from tests.integration.test_audit_tahap2 import _batal
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    q, t = _kuota_pending(db, k)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    assert t.id_transaksi is not None and q.kuota_terpakai == 1
    hasil = _hak(db, t, staf)
    db.refresh(t); db.refresh(q)
    assert V(t.status_tindakan) == "BATAL" and q.kuota_terpakai == 0
    assert hasil["data"]["bentuk"] == "KUOTA"
    assert _prabayar_dari(db, t) == []
    with pytest.raises(HTTPException):                # sudah ada pembayaran → ditolak
        _batal(db, k, staf)
    bereskan_kunjungan(db, AuditService(db), k.id_kunjungan, actor_id_staf=staf.id_staf,
                       request=None)                  # langsung: BATAL dilewati
    db.refresh(q)
    assert q.kuota_terpakai == 0


def test_sesi_2_series_prabayar_kembali_pending(db):
    """P1: sesi 2..N (Rp 0) → sesinya kembali PENDING, bisa dipakai lagi; tanpa hak baru."""
    staf, k0 = _siapkan(db)
    s1 = _rencana(db, k0, 1, k0.id_kunjungan, "DONE")
    s2 = _rencana(db, k0, 2, k0.id_kunjungan, "SCHEDULED")
    _, k = _siapkan(db)
    k.id_pasien = k0.id_pasien; db.flush()
    s1.id_pasien = s2.id_pasien = k0.id_pasien
    s2.id_kunjungan_eksekusi = k.id_kunjungan; db.flush()
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s2.id_treatment,
                          id_rencana=s2.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)    # Rp 0
    db.refresh(t)
    assert t.id_transaksi is not None
    hasil = _hak(db, t, staf)
    db.refresh(t); db.refresh(s2); db.refresh(s1)
    assert V(t.status_tindakan) == "BATAL"
    assert V(s2.status) == "PENDING" and s2.id_kunjungan_eksekusi is None
    assert V(s1.status) == "DONE"
    assert hasil["data"]["bentuk"] == "SESI"
    assert _prabayar_dari(db, t) == []


def test_sesi_1_paket_jadi_hak_series_tetap_hidup(db):
    """P2: sesi 1 (pembawa harga paket) dibayar lalu ditolak → sesi 1 kembali PENDING,
    sesi 2..N TIDAK dibatalkan (beda dengan Batalkan sebelum bayar, yang membatalkan series)."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    s3 = _rencana(db, k, 3, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    hasil = _hak(db, t, staf)
    for x in (t, s1, s2, s3, k):
        db.refresh(x)
    assert V(t.status_tindakan) == "BATAL"
    assert [V(x.status) for x in (s1, s2, s3)] == ["PENDING", "PENDING", "PENDING"]
    assert hasil["data"]["bentuk"] == "SESI"
    assert _prabayar_dari(db, t) == []
    assert V(k.status_antrian) == "COMPLETED"


def test_rencana_tak_bisa_dikembalikan_ditolak_tanpa_perubahan(db):
    """Sesi yang sudah tidak SCHEDULED (data ganjil) → 409, bukan BATAL diam-diam yang
    menghapus hak pasien tanpa pengganti."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "CANCELLED")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    with pytest.raises(HTTPException) as e:
        _hak(db, t, staf)
    assert e.value.status_code == 409
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING"


def test_belum_dibayar_ditolak_dan_menunjuk_batalkan(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    with pytest.raises(HTTPException) as e:
        _hak(db, t, staf)
    assert e.value.status_code == 400 and "Batalkan" in e.value.detail
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING"


@pytest.mark.parametrize("status", ["PROSES", "SELESAI"])
def test_sudah_dikerjakan_ditolak(db, status):
    staf, k, t = _dibayar_di_muka(db, status)
    with pytest.raises(HTTPException) as e:
        _hak(db, t, staf)
    assert e.value.status_code == 400
    db.refresh(t)
    assert V(t.status_tindakan) == status
    assert _prabayar_dari(db, t) == []


def test_hak_dua_kali_ditolak(db):
    staf, k, t = _dibayar_di_muka(db)
    _hak(db, t, staf)
    with pytest.raises(HTTPException) as e:
        _hak(db, t, staf)
    assert e.value.status_code == 400
    assert len(_prabayar_dari(db, t)) == 1


def test_alasan_wajib(db):
    staf, k, t = _dibayar_di_muka(db)
    with pytest.raises(HTTPException) as e:
        _hak(db, t, staf, alasan="  ")
    assert e.value.status_code == 400
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING"


def test_batalkan_tindakan_dibayar_menunjuk_simpan_hak(db):
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan
    staf, k, t = _dibayar_di_muka(db)
    with pytest.raises(HTTPException) as e:
        _batalkan(db, t, staf)
    assert e.value.status_code == 400
    assert "sudah dibayar" in e.value.detail and "Simpan sebagai hak" in e.value.detail


def test_hak_mengunci_kunjungan_sebelum_tindakan(db):
    """Urutan kunci sama dengan Batalkan/bayar/void: potret ditutup, kunjungan, tindakan."""
    from tests.integration.test_audit_tahap3 import _berkunci
    from tests.integration.test_audit_tahap4 import _rekam_dengan_commit
    staf, k, t = _dibayar_di_muka(db)
    q = _rekam_dengan_commit(db, lambda: _hak(db, t, staf))
    i_commit = q.index("<<COMMIT>>")
    i_kj = q.index(_berkunci(q, "kunjungan")[0])
    i_t = q.index(_berkunci(q, "kunjungan_tindakan")[0])
    assert i_commit < i_kj < i_t
    assert not [x for x in q[i_commit + 1:i_kj] if x.startswith("SELECT")]


def test_konsul_diserahkan_lalu_tindakan_jadi_hak_completed(db):
    """Alur klinik yang memicu tahap 4: konsul+obat+tindakan dibayar sekali, obat
    diserahkan, pasien menolak tindakan → kunjungan selesai."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    _resep(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    _serah(db, k, staf)
    db.refresh(k); db.refresh(t)
    assert V(k.status_antrian) == "ANTRI_TREATMENT"
    _hak(db, t, staf)
    db.refresh(k)
    assert V(k.status_antrian) == "COMPLETED"


@pytest.mark.parametrize("awal,harapan", [
    (date(2026, 10, 28), date(2027, 4, 28)),
    (date(2026, 8, 31), date(2027, 2, 28)),          # Februari tanpa tanggal 31
    (date(2027, 8, 31), date(2028, 2, 29)),          # kabisat
    (date(2026, 12, 15), date(2027, 6, 15)),
])
def test_tambah_bulan(awal, harapan):
    from app.services.treatment_service import tambah_bulan
    assert tambah_bulan(awal, 6) == harapan


def test_tanggal_dari_waktu_bayar_bukan_hari_ini(db):
    """Batas hak = tanggal BAYAR + 6 bulan (spek §3.6), bukan tanggal tombol ditekan."""
    from datetime import timedelta
    from app.services.treatment_service import tambah_bulan
    staf, k, t = _dibayar_di_muka(db)
    trx = _trx_terakhir(db, k)
    trx.waktu_bayar = datetime.now() - timedelta(days=40); db.flush()
    _hak(db, t, staf)
    h = _prabayar_dari(db, t)[0]
    assert h.tgl_target_akhir == tambah_bulan(trx.waktu_bayar.date(), 6)
    assert h.tgl_target_akhir != tambah_bulan(date.today(), 6)
