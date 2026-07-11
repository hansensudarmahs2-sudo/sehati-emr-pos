"""
Booking L2 — test BookingService (gate membership + CRUD + reschedule).
Non-destruktif: rollback di teardown. Run:
    .venv/bin/pytest tests/integration/test_booking_service.py -v
"""
import random
import time as _t
from datetime import date, time

import pytest
from fastapi import HTTPException

from app.db.session import SessionLocal
from app.db.models import Pasien
from app.db.models._enums import MembershipTierEnum, StatusBookingEnum
from app.services.booking_service import BookingService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _mk_pasien(db, tier: MembershipTierEnum):
    rm = f"BKT-{int(_t.time())}-{random.randint(100, 999)}"
    p = Pasien(no_rm=rm, nama=f"Booking Test {tier.value}", tipe_membership=tier)
    db.add(p)
    db.flush()
    return p


def _status(b):
    return b.status_booking.value if hasattr(b.status_booking, "value") else str(b.status_booking)


def test_gate_regular_ditolak(db):
    p = _mk_pasien(db, MembershipTierEnum.REGULAR)
    svc = BookingService(db)
    with pytest.raises(HTTPException) as e:
        svc.create(p.id_pasien, date.today(), time(10, 0), actor_id_staf=None)
    assert e.value.status_code == 400


def test_create_dan_list(db):
    p = _mk_pasien(db, MembershipTierEnum.VIP)
    svc = BookingService(db)
    b = svc.create(p.id_pasien, date.today(), "10:30", keluhan_utama="kontrol", actor_id_staf=None)
    assert _status(b) == "BOOKED"
    items = svc.list_tanggal(date.today())
    assert any(it["id_booking"] == b.id_booking and it["jam"] == "10:30" for it in items)
    # muncul di list_bulan
    bulan = svc.list_bulan(date.today().year, date.today().month)
    assert date.today().isoformat() in bulan


def test_confirm_cancel(db):
    p = _mk_pasien(db, MembershipTierEnum.VVIP)
    svc = BookingService(db)
    b = svc.create(p.id_pasien, date.today(), "09:00", actor_id_staf=None)
    svc.confirm(b.id_booking)
    assert _status(svc.get(b.id_booking)) == "CONFIRMED"
    svc.cancel(b.id_booking)
    assert _status(svc.get(b.id_booking)) == "CANCELLED"


def test_reschedule_link(db):
    p = _mk_pasien(db, MembershipTierEnum.VIP)
    svc = BookingService(db)
    old = svc.create(p.id_pasien, date.today(), "08:00", actor_id_staf=None)
    new = svc.reschedule(old.id_booking, date.today(), "13:00", actor_id_staf=None)
    assert _status(svc.get(old.id_booking)) == "RESCHEDULED"
    assert _status(new) == "BOOKED"
    assert new.id_booking_lama == old.id_booking
    assert new.jam_rencana.strftime("%H:%M") == "13:00"


def test_checkin_konsul_buat_antrian(db):
    """L4: check-in booking → Kunjungan (ANTRI_KONSULTASI) + booking CHECKED_IN."""
    from app.db.models import Kunjungan
    p = _mk_pasien(db, MembershipTierEnum.VIP)
    svc = BookingService(db)
    b = svc.create(p.id_pasien, date.today(), "11:00", keluhan_utama="kontrol rutin", actor_id_staf=None)
    # butuh id_staf valid untuk id_staf_fo → pakai staf pertama yang ada
    from app.db.models import MasterStaf
    staf = db.query(MasterStaf).first()
    res = svc.check_in(b.id_booking, status_antrian="ANTRI_KONSULTASI",
                       actor_id_staf=(staf.id_staf if staf else None))
    assert _status(svc.get(b.id_booking)) == "CHECKED_IN"
    data = res.get("data", {}) if isinstance(res, dict) else {}
    assert data.get("id_kunjungan") or data.get("nomor_antrean")
    # kunjungan benar-benar dibuat hari ini untuk pasien
    kj = db.query(Kunjungan).filter(Kunjungan.id_pasien == p.id_pasien).first()
    assert kj is not None
    assert kj.status_antrian in ("ANTRI_KONSULTASI",)


def test_checkin_ditolak_kalau_sudah_checkin(db):
    from app.db.models import MasterStaf
    p = _mk_pasien(db, MembershipTierEnum.VVIP)
    svc = BookingService(db)
    b = svc.create(p.id_pasien, date.today(), "12:00", actor_id_staf=None)
    staf = db.query(MasterStaf).first()
    aid = staf.id_staf if staf else None
    svc.check_in(b.id_booking, status_antrian="ANTRI_TREATMENT", actor_id_staf=aid)
    with pytest.raises(HTTPException) as e:
        svc.check_in(b.id_booking, status_antrian="ANTRI_KONSULTASI", actor_id_staf=aid)
    assert e.value.status_code == 400


def test_checkin_ditolak_kalau_bukan_hari_h(db):
    """Booking tanggal depan tak boleh check-in hari ini."""
    from datetime import timedelta
    from app.db.models import MasterStaf
    p = _mk_pasien(db, MembershipTierEnum.VIP)
    svc = BookingService(db)
    besok = date.today() + timedelta(days=2)
    b = svc.create(p.id_pasien, besok, "10:00", actor_id_staf=None)
    staf = db.query(MasterStaf).first()
    with pytest.raises(HTTPException) as e:
        svc.check_in(b.id_booking, status_antrian="ANTRI_KONSULTASI",
                     actor_id_staf=(staf.id_staf if staf else None))
    assert e.value.status_code == 400
    assert "belum bisa check-in" in str(e.value.detail).lower()
    # booking tetap BOOKED (tidak berubah)
    assert _status(svc.get(b.id_booking)) == "BOOKED"
