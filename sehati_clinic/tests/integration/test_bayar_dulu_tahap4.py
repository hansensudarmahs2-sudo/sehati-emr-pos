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


# ---------------------------------------------------------------- T4-2 Memakai hak
# Hak yang lahir di T4-1 dipakai lewat "Pakai Sesi" di kunjungan lain. Dulu (sebelum T4-2):
# hak PRABAYAR ditagih harga treatment LAGI (`_compute_charge`: rencana sesi 1 = harga
# paket × jumlah sesi), sesi 1 paket yang kembali PENDING ditagih harga paket LAGI, semua hak
# satu treatment digabung jadi satu baris, dan hak kedaluwarsa tetap bisa dipakai.
def _kunjungan_lain(db, k, staf, status="ANTRI_TREATMENT"):
    from app.db.models import Kunjungan
    k2 = Kunjungan(id_pasien=k.id_pasien, status_antrian=status,
                   id_staf_fo=staf.id_staf, nomor_antrean=997)
    db.add(k2); db.flush()
    return k2


def _pakai(db, rencana, k2, staf):
    from app.services.series_service import SeriesService
    SeriesService(db).use_session(rencana.id_rencana, k2.id_kunjungan, staf.id_staf)
    return db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k2.id_kunjungan,
        KunjunganTindakan.id_rencana == rencana.id_rencana,
        KunjunganTindakan.status_tindakan != "BATAL")).scalar_one()


def _harga_di_tagihan(db, k, t):
    from app.services.kasir_service import KasirService
    tagihan = KasirService(db).get_tagihan(k.id_kunjungan)
    return [r.harga for r in tagihan.rincian_tindakan if r.id_kunjungan_tindakan == t.id_kunjungan_tindakan]


def _hak_dari_tindakan_baru(db):
    staf, k, t = _dibayar_di_muka(db)
    _hak(db, t, staf)
    return staf, k, t, _prabayar_dari(db, t)[0]


def test_hak_dipakai_ditagih_rp0_dan_berkomisi(db):
    from tests.integration.test_bayar_dulu_tahap2 import _beri_komisi, _kerjakan, _komisi
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    k2 = _kunjungan_lain(db, k, staf)
    t2 = _pakai(db, h, k2, staf)
    _beri_komisi(db, t2, staf)                        # master uji tanpa komisi (lihat helper)
    db.refresh(h)
    assert V(h.status) == "SCHEDULED"
    assert _harga_di_tagihan(db, k2, t2) == [0]       # dulu: harga treatment lagi
    _bayar(db, k2, staf, konfirmasi_prabayar=True)
    db.refresh(t2)
    assert t2.id_transaksi is not None
    _kerjakan(db, t2, staf)
    assert len(_komisi(db, t2)) == 1                  # seperti sesi series Rp 0: basis master


def test_hak_kedaluwarsa_tidak_tampil_dan_ditolak(db):
    from datetime import timedelta
    from app.services.series_service import SeriesService
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    svc = SeriesService(db)
    assert [g["id_rencana_hak"] for g in svc.list_active_for_pasien(k.id_pasien)
            if g["jenis"] == "HAK"] == [h.id_rencana]
    h.tgl_target_akhir = date.today() - timedelta(days=1); db.flush()
    assert [g for g in svc.list_active_for_pasien(k.id_pasien) if g["jenis"] == "HAK"] == []
    k2 = _kunjungan_lain(db, k, staf)
    with pytest.raises(HTTPException) as e:
        svc.use_session(h.id_rencana, k2.id_kunjungan, staf.id_staf)
    assert e.value.status_code == 409 and "kedaluwarsa" in e.value.detail.lower()
    db.refresh(h)
    assert V(h.status) == "PENDING"


def test_hak_hari_terakhir_masih_berlaku(db):
    from app.services.series_service import SeriesService
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    h.tgl_target_akhir = date.today(); db.flush()
    k2 = _kunjungan_lain(db, k, staf)
    _pakai(db, h, k2, staf)


def test_hak_tampil_per_rencana_dengan_nilai_dan_batas(db):
    """Dua hak treatment yang sama = dua baris (dulu: digabung per treatment, tombol hanya
    untuk yang pertama). Nilai = subtotal BERSIH yang dibayar (snapshot)."""
    from app.db.models import TransaksiDetailTindakan
    from app.services.series_service import SeriesService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t1 = _tindakan_baru(db, k, "PENDING")
    t2 = _tindakan_baru(db, k, "PENDING")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t1); db.refresh(t2)
    _hak(db, t1, staf); _hak(db, t2, staf)
    hak = [g for g in SeriesService(db).list_active_for_pasien(k.id_pasien) if g["jenis"] == "HAK"]
    assert len(hak) == 2
    for g, t in zip(sorted(hak, key=lambda g: g["id_rencana_hak"]), (t1, t2)):
        sub = db.execute(select(TransaksiDetailTindakan.subtotal).where(
            TransaksiDetailTindakan.id_kunjungan_tindakan == t.id_kunjungan_tindakan)).scalar_one()
        assert g["nilai"] == float(sub)
        assert g["berlaku_sampai"] == _prabayar_dari(db, t)[0].tgl_target_akhir
        assert g["sisa_hari"] > 0
        assert [r["id_rencana"] for r in g["rencana_pending"]] == [g["id_rencana_hak"]]


def test_hak_dan_series_dokter_treatment_sama_tidak_saling_mengubah_harga(db):
    """Keputusan T4-1 `id_kunjungan_pembuat = NULL`: hak dan series dokter treatment yang
    SAMA di kunjungan yang SAMA. Harga paket series tetap per_sesi × 3, hak Rp 0, dan
    keduanya tampil terpisah."""
    from decimal import Decimal
    from app.db.models import MasterTreatment
    from app.services.series_service import SeriesService
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    k2 = _kunjungan_lain(db, k, staf, "ANTRI_BAYAR")
    _soap(db, k2, staf)
    sesi = []
    for i, st in ((1, "SCHEDULED"), (2, "PENDING"), (3, "PENDING")):
        r = PasienRencanaTreatment(id_pasien=k.id_pasien, id_treatment=h.id_treatment,
                                   urutan_sesi=i, nama_tindakan="Uji Series",
                                   id_kunjungan_pembuat=k2.id_kunjungan, status=st)
        db.add(r); db.flush(); sesi.append(r)
    ts1 = KunjunganTindakan(id_kunjungan=k2.id_kunjungan, id_treatment=h.id_treatment,
                            id_rencana=sesi[0].id_rencana, status_tindakan="PENDING")
    db.add(ts1); db.flush()
    th = _pakai(db, h, k2, staf)
    tr = db.get(MasterTreatment, h.id_treatment)
    per_sesi = Decimal(str(tr.harga_paket if tr.harga_paket is not None else tr.harga))
    assert _harga_di_tagihan(db, k2, ts1) == [per_sesi * 3]
    assert _harga_di_tagihan(db, k2, th) == [0]
    jenis = sorted(g["jenis"] for g in SeriesService(db).list_active_for_pasien(k.id_pasien))
    assert jenis == ["SERIES"]                        # hak sudah dipakai (SCHEDULED)


def test_sesi_1_paket_yang_jadi_hak_dipakai_lagi_rp0(db):
    """P2: sesi 1 paket lunas → hak (kembali PENDING) → dipakai di kunjungan lain: Rp 0,
    dan sesi 2 tetap boleh dipakai (paket memang sudah lunas)."""
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    _hak(db, t, staf)
    k2 = _kunjungan_lain(db, k, staf)
    t1b = _pakai(db, s1, k2, staf)
    assert _harga_di_tagihan(db, k2, t1b) == [0]      # dulu: harga paket lagi
    k3 = _kunjungan_lain(db, k, staf)
    _pakai(db, s2, k3, staf)


@pytest.mark.parametrize("status_trx", [None, "VOID"])
def test_sesi_1_yang_belum_pernah_lunas_tetap_harga_paket(db, status_trx):
    """Pembanding: "pernah lunas" = tindakan BATAL lain ber-transaksi BAYAR. Tindakan batal
    tanpa transaksi, atau transaksinya VOID, BUKAN bukti lunas."""
    from decimal import Decimal
    from app.db.models import MasterTreatment
    from app.services._series import jumlah_sesi
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    t0 = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                           id_rencana=s1.id_rencana, status_tindakan="BATAL")
    db.add(t0); db.flush()
    if status_trx:
        _resep(db, k, staf)
        _bayar(db, k, staf)
        trx = _trx_terakhir(db, k)
        trx.status_transaksi = status_trx
        t0.id_transaksi = trx.id_transaksi; db.flush()
    t1 = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                           id_rencana=s1.id_rencana, status_tindakan="PENDING")
    db.add(t1); db.flush()
    tr = db.get(MasterTreatment, s1.id_treatment)
    per_sesi = Decimal(str(tr.harga_paket if tr.harga_paket is not None else tr.harga))
    assert _harga_di_tagihan(db, k, t1) == [per_sesi * jumlah_sesi(db, s1)]


def test_nota_hak_ditulis_hak_prabayar_bukan_paket_series(db):
    from app.services.print_service import PrintService
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    k2 = _kunjungan_lain(db, k, staf)
    t2 = _pakai(db, h, k2, staf)
    _bayar(db, k2, staf, konfirmasi_prabayar=True)
    snap = PrintService(db)._baris_snapshot(_trx_terakhir(db, k2).id_transaksi)
    baris = [i for i in snap["items"] if i["tipe"] == "TND"]
    assert len(baris) == 1 and baris[0]["harga"] == 0
    assert baris[0]["ket_prabayar"].startswith("Hak prabayar")
    assert baris[0]["ket_dimuka"] is None


def test_hak_dipakai_lalu_batalkan_kembali_jadi_hak(db):
    """Hak dipakai di kunjungan lain, belum dibayar, pasien menolak lagi → Batalkan →
    haknya kembali PENDING (tidak hilang, tidak dibatalkan)."""
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    k2 = _kunjungan_lain(db, k, staf)
    t2 = _pakai(db, h, k2, staf)
    _batalkan(db, t2, staf)
    db.refresh(h)
    assert V(h.status) == "PENDING"


def test_sesi_1_lunas_dipakai_lagi_di_kunjungan_sama_lalu_batalkan_series_hidup(db):
    """Sesi 1 paket lunas → hak → dipakai lagi di kunjungan PEMBUAT yang sama (masih aktif
    karena ada tindakan lain) → Batalkan. Dulu `bereskan_satu_tindakan` membaca "sesi 1 yang
    lahir di kunjungan ini, belum dibayar" → seluruh series CANCELLED padahal paketnya lunas."""
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
    s2 = _rencana(db, k, 2, k.id_kunjungan, "PENDING")
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                          id_rencana=s1.id_rencana, status_tindakan="PENDING")
    lain = _tindakan_baru(db, k, "PENDING")           # menahan kunjungan tetap aktif
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    _hak(db, t, staf)
    db.refresh(k)
    assert V(k.status_antrian) not in ("COMPLETED", "BATAL")
    t1b = _pakai(db, s1, k, staf)
    _batalkan(db, t1b, staf)
    db.refresh(s1); db.refresh(s2); db.refresh(lain)
    assert V(s1.status) == "PENDING" and V(s2.status) == "PENDING"


# ---------------------------------------------------------------- T4-3 Kembalikan uang per tindakan
# Tiga asal, satu fungsi (`KasirService.refund_tindakan`):
#   A. tindakan PENDING yang sudah dibayar (id_kunjungan_tindakan);
#   B. hak PRABAYAR yang belum dipakai & belum kedaluwarsa (id_rencana);
#   C. sesi 1 paket yang lunas lalu disimpan sebagai hak (id_rencana, P2).
# Nilai = snapshot `transaksi_detail_tindakan.subtotal` (BERSIH). Header transaksi TIDAK
# disentuh (T32); uang keluar di TANGGAL refund lewat `_refund_bukuan`. PIN hanya untuk
# transaksi hari lampau (P3).
def _refund(db, staf, *, t=None, rencana=None, **kw):
    from app.services.kasir_service import KasirService
    kw.setdefault("alasan", "pasien minta uang kembali")
    return KasirService(db).refund_tindakan(
        id_kunjungan_tindakan=t.id_kunjungan_tindakan if t is not None else None,
        id_rencana=rencana.id_rencana if rencana is not None else None,
        actor_id_staf=staf.id_staf, **kw)


def _refund_rows(db, t):
    from app.db.models import TransaksiRefund
    return db.execute(select(TransaksiRefund).where(
        TransaksiRefund.id_kunjungan_tindakan == t.id_kunjungan_tindakan)).scalars().all()


def _subtotal(db, t):
    from app.db.models import TransaksiDetailTindakan
    return db.execute(select(TransaksiDetailTindakan.subtotal).where(
        TransaksiDetailTindakan.id_kunjungan_tindakan == t.id_kunjungan_tindakan,
        TransaksiDetailTindakan.id_transaksi == t.id_transaksi)).scalar_one()


def _kemarin(db, k):
    from datetime import timedelta
    trx = _trx_terakhir(db, k)
    trx.waktu_bayar = trx.waktu_bayar - timedelta(days=1); db.flush()
    return trx


def test_refund_tindakan_prabayar_nilai_bersih_header_utuh(db, monkeypatch):
    """Diskon member 10% atas dua tindakan: refund satu = subtotal BERSIH-nya, bukan harga
    master; header transaksi tidak berubah; tindakan BATAL; kunjungan bisa selesai."""
    from decimal import Decimal
    from app.services.membership_service import DiskonMembership, MembershipService
    monkeypatch.setattr(MembershipService, "get_diskon_for_pasien",
                        lambda self, i: DiskonMembership(Decimal("10"), Decimal("0"), "UJI", True))
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t1 = _tindakan_baru(db, k, "PENDING")
    t2 = _tindakan_baru(db, k, "PENDING")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    trx = _trx_terakhir(db, k)
    total_awal = trx.total_tagihan
    db.refresh(t1); db.refresh(t2)
    sub = _subtotal(db, t1)
    from app.db.models import MasterTreatment
    assert sub < Decimal(str(db.get(MasterTreatment, t1.id_treatment).harga))   # diskon nyata
    hasil = _refund(db, staf, t=t1, metode_refund="TUNAI")
    db.refresh(trx); db.refresh(t1); db.refresh(k)
    rows = _refund_rows(db, t1)
    assert len(rows) == 1
    r = rows[0]
    assert (r.jenis_refund, Decimal(str(r.nilai_refund)), r.id_transaksi, r.metode_refund) \
        == ("TINDAKAN", Decimal(str(sub)), trx.id_transaksi, "TUNAI")
    assert r.id_staf_otorisasi is None                # hari yang sama: tanpa PIN
    assert trx.total_tagihan == total_awal            # T32: header tidak disentuh
    assert V(t1.status_tindakan) == "BATAL"
    assert V(k.status_antrian) == "ANTRI_TREATMENT"   # t2 masih menunggu
    assert hasil["data"]["nilai_refund"] == float(sub)
    log = db.execute(select(AuditLog).where(AuditLog.aksi == "REFUND_TINDAKAN",
                                            AuditLog.id_target == trx.id_transaksi)).scalar_one()
    assert str(t1.id_kunjungan_tindakan) in str(log.data_baru)


def test_refund_dibukukan_di_tanggal_refund_dan_keluar_laci(db):
    """Transaksi kemarin, refund hari ini (PIN): omzet KEMARIN tidak berubah, refund hari
    ini bertambah, dan metode refund masuk hitungan laci (refund_per_metode)."""
    from datetime import datetime, time, timedelta
    from decimal import Decimal
    from app.services import _refund_bukuan as rb
    from tests.integration.test_bayar_dulu_tahap2 import _penyetuju
    staf, k, t = _dibayar_di_muka(db)
    trx = _kemarin(db, k)
    hari_ini = (datetime.combine(date.today(), time.min), datetime.combine(date.today(), time.max))
    kemarin = (hari_ini[0] - timedelta(days=1), hari_ini[1] - timedelta(days=1))
    ref_kemarin, ref_ini = rb.refund_total(db, *kemarin), rb.refund_total(db, *hari_ini)
    laci_ini = rb.refund_per_metode(db, *hari_ini).get("TUNAI", Decimal("0"))
    admin, sup = _penyetuju(db)
    _refund(db, admin, t=t, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    sub = Decimal(str(_subtotal(db, t)))
    assert rb.refund_total(db, *kemarin) == ref_kemarin
    assert rb.refund_total(db, *hari_ini) == ref_ini + sub
    assert rb.refund_per_metode(db, *hari_ini).get("TUNAI") == laci_ini + sub
    assert _refund_rows(db, t)[0].id_staf_otorisasi == sup.id_staf


def test_refund_hari_lampau_wajib_pin_penyetuju_lain(db):
    from tests.integration.test_bayar_dulu_tahap2 import _penyetuju
    staf, k, t = _dibayar_di_muka(db)
    _kemarin(db, k)
    admin, sup = _penyetuju(db)
    with pytest.raises(HTTPException) as e:
        _refund(db, admin, t=t)
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        _refund(db, sup, t=t, id_staf_otorisasi=sup.id_staf, pin_otorisasi="4321")
    assert e.value.status_code == 400                 # penyetuju = pemroses
    db.refresh(t)
    assert V(t.status_tindakan) == "PENDING" and _refund_rows(db, t) == []


def test_refund_dua_kali_ditolak(db):
    staf, k, t = _dibayar_di_muka(db)
    _refund(db, staf, t=t)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t)
    assert e.value.status_code == 400
    assert len(_refund_rows(db, t)) == 1


def test_refund_menyelesaikan_kunjungan_dan_void_lalu_ditolak(db):
    from tests.integration.test_audit_tahap2 import _void
    staf, k, t = _dibayar_di_muka(db)
    _refund(db, staf, t=t)
    db.refresh(k)
    assert V(k.status_antrian) == "COMPLETED"
    with pytest.raises(HTTPException):                # _pagari_void_sudah_refund
        _void(db, _trx_terakhir(db, k).id_transaksi, staf)


@pytest.mark.parametrize("status", ["PROSES", "SELESAI"])
def test_refund_tindakan_sudah_dikerjakan_ditolak(db, status):
    staf, k, t = _dibayar_di_muka(db, status)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t)
    assert e.value.status_code == 400 and _refund_rows(db, t) == []


def test_refund_belum_dibayar_ditolak(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t)
    assert e.value.status_code == 400 and "belum dibayar" in e.value.detail


def test_refund_kuota_rp0_ditolak_menunjuk_simpan_hak(db):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    q, t = _kuota_pending(db, k)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t)
    assert e.value.status_code == 400 and "Simpan sebagai hak" in e.value.detail


def test_refund_metode_tidak_sah_ditolak(db):
    staf, k, t = _dibayar_di_muka(db)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t, metode_refund="BARTER")
    assert e.value.status_code == 400


def test_refund_alasan_wajib(db):
    staf, k, t = _dibayar_di_muka(db)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t, alasan=" ")
    assert e.value.status_code == 400


def test_refund_hak_prabayar(db):
    """B: hak yang belum dipakai → uang kembali, hak CANCELLED, refund menunjuk tindakan
    ASAL hak (bukan rencana) — supaya anti-dobel dan ekspor punya satu jangkar."""
    from decimal import Decimal
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    _refund(db, staf, rencana=h)
    db.refresh(h)
    assert V(h.status) == "CANCELLED"
    rows = _refund_rows(db, t)
    assert len(rows) == 1 and rows[0].jenis_refund == "TINDAKAN"
    assert Decimal(str(rows[0].nilai_refund)) == Decimal(str(_subtotal(db, t)))
    with pytest.raises(HTTPException):
        _refund(db, staf, rencana=h)


def test_refund_hak_kedaluwarsa_atau_terpakai_ditolak(db):
    from datetime import timedelta
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    h.tgl_target_akhir = date.today() - timedelta(days=1); db.flush()
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, rencana=h)
    assert e.value.status_code == 400 and "kedaluwarsa" in e.value.detail.lower()
    h.tgl_target_akhir = date.today(); db.flush()
    k2 = _kunjungan_lain(db, k, staf)
    _pakai(db, h, k2, staf)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, rencana=h)
    assert e.value.status_code == 400
    assert _refund_rows(db, t) == []


def test_refund_tindakan_dari_hak_rp0_ditolak(db):
    """Tindakan yang memakai hak dibayar Rp 0 — uangnya ada di hak asal. Ditolak dengan
    petunjuk: simpan sebagai hak dulu (hak kembali), lalu kembalikan uang haknya."""
    staf, k, t, h = _hak_dari_tindakan_baru(db)
    k2 = _kunjungan_lain(db, k, staf)
    t2 = _pakai(db, h, k2, staf)
    _bayar(db, k2, staf, konfirmasi_prabayar=True)
    db.refresh(t2)
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t2)
    assert e.value.status_code == 400 and "Simpan sebagai hak" in e.value.detail


def _series_lunas(db, n=3):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    sesi = [_rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")]
    sesi += [_rencana(db, k, i, k.id_kunjungan, "PENDING") for i in range(2, n + 1)]
    t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=sesi[0].id_treatment,
                          id_rencana=sesi[0].id_rencana, status_tindakan="PENDING")
    db.add(t); db.flush()
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    return staf, k, t, sesi


def test_refund_sesi_1_paket_membatalkan_series(db):
    """P2: sesi 1 (harga paket) dibayar, belum ada sesi lain terpakai → refund SELURUH
    paket (snapshot), semua sesi CANCELLED."""
    from decimal import Decimal
    staf, k, t, sesi = _series_lunas(db)
    _refund(db, staf, t=t)
    for s in sesi:
        db.refresh(s)
    assert [V(s.status) for s in sesi] == ["CANCELLED"] * 3
    assert Decimal(str(_refund_rows(db, t)[0].nilai_refund)) == Decimal(str(_subtotal(db, t)))


def test_refund_sesi_1_ditolak_bila_sesi_lain_terpakai(db):
    staf, k, t, sesi = _series_lunas(db)
    sesi[1].status = "SCHEDULED"; db.flush()          # sesi 2 sudah dipakai di kunjungan lain
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, t=t)
    assert e.value.status_code == 400 and "Simpan sebagai hak" in e.value.detail
    db.refresh(sesi[0])
    assert V(sesi[0].status) == "SCHEDULED" and _refund_rows(db, t) == []


def test_refund_sesi_1_yang_sudah_jadi_hak(db):
    """C: sesi 1 lunas → simpan sebagai hak (sesi 1 PENDING lagi) → uang kembali lewat
    rencana sesi 1; series dibatalkan; refund menunjuk tindakan lunas asalnya."""
    staf, k, t, sesi = _series_lunas(db)
    _hak(db, t, staf)
    _refund(db, staf, rencana=sesi[0])
    for s in sesi:
        db.refresh(s)
    assert [V(s.status) for s in sesi] == ["CANCELLED"] * 3
    assert len(_refund_rows(db, t)) == 1


def test_refund_sesi_series_dokter_tanpa_pernah_lunas_ditolak(db):
    """Rencana series dokter biasa (belum pernah lunas) bukan hak — tidak bisa direfund."""
    staf, k = _siapkan(db)
    s1 = _rencana(db, k, 1, k.id_kunjungan, "PENDING")
    with pytest.raises(HTTPException) as e:
        _refund(db, staf, rencana=s1)
    assert e.value.status_code == 400


def test_refund_mengunci_kunjungan_sebelum_tindakan(db):
    from tests.integration.test_audit_tahap3 import _berkunci
    from tests.integration.test_audit_tahap4 import _rekam_dengan_commit
    staf, k, t = _dibayar_di_muka(db)
    q = _rekam_dengan_commit(db, lambda: _refund(db, staf, t=t))
    i_commit = q.index("<<COMMIT>>")
    i_kj = q.index(_berkunci(q, "kunjungan")[0])
    i_t = q.index(_berkunci(q, "kunjungan_tindakan")[0])
    i_r = q.index(_berkunci(q, "transaksi_refund")[0])
    assert i_commit < i_kj < i_t < i_r
    assert not [x for x in q[i_commit + 1:i_kj] if x.startswith("SELECT")]


def test_daftar_bisa_direfund_satu_definisi_dengan_refund(db):
    """Kotak di halaman tagihan memakai pemeriksaan yang SAMA dengan refund: yang ditawarkan
    pasti diterima, yang tidak ditawarkan membawa alasan."""
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    q, tk = _kuota_pending(db, k)
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    daftar = {d["id_kunjungan_tindakan"]: d for d in KasirService(db).tindakan_bisa_direfund(k.id_kunjungan)}
    assert daftar[t.id_kunjungan_tindakan]["bisa"] is True
    assert daftar[t.id_kunjungan_tindakan]["nilai"] > 0
    assert daftar[tk.id_kunjungan_tindakan]["bisa"] is False
    assert "Simpan sebagai hak" in daftar[tk.id_kunjungan_tindakan]["alasan_tidak"]


# ---------------------------------------------------------------- T4-4 Pagar void
# Tindakan yang sudah dijadikan hak (atau kuota/sesinya dikembalikan) sesudah dibayar: void
# transaksinya mengeluarkan SELURUH uang dari omzet, sementara hak gratisnya tetap ada →
# pasien mendapat tindakan gratis. Refund sudah tertutup `_pagari_void_sudah_refund`.
def _void_jalur(db, trx, staf, jalur):
    from tests.integration.test_bayar_dulu_tahap2 import _void_t24
    return _void_t24(db, trx, staf, jalur)


@pytest.mark.parametrize("jalur", ["void", "force", "lampau"])
@pytest.mark.parametrize("bentuk", ["HAK", "KUOTA", "SESI"])
def test_void_ditolak_bila_tindakan_sudah_jadi_hak(db, jalur, bentuk):
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    if bentuk == "HAK":
        t = _tindakan_baru(db, k, "PENDING")
    elif bentuk == "KUOTA":
        q, t = _kuota_pending(db, k)
    else:
        s1 = _rencana(db, k, 1, k.id_kunjungan, "SCHEDULED")
        t = KunjunganTindakan(id_kunjungan=k.id_kunjungan, id_treatment=s1.id_treatment,
                              id_rencana=s1.id_rencana, status_tindakan="PENDING")
        db.add(t); db.flush()
    _resep(db, k, staf)                               # transaksi juga memuat obat
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    db.refresh(t)
    _hak(db, t, staf)
    trx = _trx_terakhir(db, k)
    with pytest.raises(HTTPException) as e:
        _void_jalur(db, trx, staf, jalur)
    assert e.value.status_code == 400 and "hak" in e.value.detail.lower()
    db.refresh(trx); db.refresh(t)
    assert V(trx.status_transaksi) == "BAYAR"
    assert V(t.status_tindakan) == "BATAL" and t.id_transaksi == trx.id_transaksi


@pytest.mark.parametrize("jalur", ["void", "force"])
def test_void_tetap_boleh_bila_tindakan_batal_sebelum_dibayar(db, jalur):
    """Pembanding: tindakan yang di-Batalkan SEBELUM bayar (BATAL tanpa transaksi) bukan
    hak — void transaksi obatnya tetap boleh."""
    from tests.integration.test_bayar_dulu_tahap1 import _batalkan
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t = _tindakan_baru(db, k, "PENDING")
    _batalkan(db, t, staf)
    _resep(db, k, staf)
    _bayar(db, k, staf)
    trx = _trx_terakhir(db, k)
    _void_jalur(db, trx, staf, jalur)
    db.refresh(trx)
    assert V(trx.status_transaksi) == "VOID"


def test_void_transaksi_lain_di_kunjungan_sama_tidak_terhalang(db):
    """Lingkup = transaksi yang MEMBAYAR tindakan itu. Hak dari transaksi T1 tidak
    menghalangi void transaksi susulan T2 yang hanya berisi obat."""
    from tests.integration.test_audit_tahap2 import _void
    staf, k, t = _dibayar_di_muka(db)
    _hak(db, t, staf)
    _resep(db, k, staf, detik=5)
    k.status_antrian = "ANTRI_BAYAR"; db.flush()
    _bayar(db, k, staf)
    t2 = _trx_terakhir(db, k)
    assert t2.id_transaksi != t.id_transaksi
    _void(db, t2.id_transaksi, staf)
    db.refresh(t2)
    assert V(t2.status_transaksi) == "VOID"


def test_peringatan_void_menyebut_tindakan_dilepas_dan_hak(db):
    """P4: layar konfirmasi void memberi tahu kasir tindakan prabayar yang akan DILEPAS
    (kembali belum ditagih) dan tindakan yang sudah jadi hak (void akan ditolak)."""
    from app.services.kasir_service import KasirService
    staf, k = _siapkan(db)
    _soap(db, k, staf)
    t1 = _tindakan_baru(db, k, "PENDING")
    t2 = _tindakan_baru(db, k, "PENDING")
    _bayar(db, k, staf, konfirmasi_prabayar=True)
    trx = _trx_terakhir(db, k)
    p = KasirService(db).peringatan_void(trx.id_transaksi)
    assert sorted(x["id_kunjungan_tindakan"] for x in p["tindakan_dilepas"]) \
        == sorted([t1.id_kunjungan_tindakan, t2.id_kunjungan_tindakan])
    assert p["tindakan_jadi_hak"] == []
    db.refresh(t1)
    _hak(db, t1, staf)
    p = KasirService(db).peringatan_void(trx.id_transaksi)
    assert [x["id_kunjungan_tindakan"] for x in p["tindakan_dilepas"]] == [t2.id_kunjungan_tindakan]
    assert [x["id_kunjungan_tindakan"] for x in p["tindakan_jadi_hak"]] == [t1.id_kunjungan_tindakan]
    assert all(x["nama"] for x in p["tindakan_dilepas"] + p["tindakan_jadi_hak"])
