"""
BookingService — modul Booking (jadwal_booking). Ref BOOKING_MODULE_DESIGN.md.

Aturan (TERKUNCI 2026-06-29):
- Gate: hanya pasien MEMBERSHIP (tipe_membership VIP/VVIP). REGULAR ditolak.
- Status: BOOKED → CONFIRMED → CHECKED_IN; cabang RESCHEDULED / CANCELLED.
- Check-in (di route/L4): buat Kunjungan (ANTRI_KONSULTASI / ANTRI_TREATMENT).
- Deposit/booking berbayar = PARKIR (kolom reserved, belum dipakai).

POLA TRANSAKSI: method mutasi FLUSH saja (audit ikut flush) — CALLER (route) yang commit.
Ini bikin service composable + mudah di-test (rollback).
"""

from datetime import date, datetime, time
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JadwalBooking, MasterStaf, Pasien
from app.db.models._enums import MembershipTierEnum, StatusBookingEnum
from app.services.audit_service import AuditService

# Tier yang boleh booking (TERKUNCI: VIP + VVIP)
MEMBERSHIP_TIERS = {"VIP", "VVIP"}


def _norm_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v).strip())


def _norm_time(v) -> time:
    if isinstance(v, time):
        return v
    s = str(v).strip()
    # terima "HH:MM" atau "HH:MM:SS"
    parts = s.split(":")
    hh, mm = int(parts[0]), int(parts[1])
    ss = int(parts[2]) if len(parts) > 2 else 0
    return time(hh, mm, ss)


def _tier_of(pasien: Pasien) -> str:
    t = pasien.tipe_membership
    return (t.value if hasattr(t, "value") else str(t or "")).upper()


class BookingService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # ---- gate ----
    def _get_pasien_membership(self, id_pasien: int) -> Pasien:
        pasien = self.db.get(Pasien, id_pasien)
        if pasien is None:
            raise HTTPException(404, f"Pasien {id_pasien} tidak ditemukan.")
        if _tier_of(pasien) not in MEMBERSHIP_TIERS:
            raise HTTPException(
                400,
                f"Booking hanya untuk member (VIP/VVIP). Pasien '{pasien.nama}' "
                f"berstatus {_tier_of(pasien) or 'REGULAR'} — tidak bisa booking.",
            )
        return pasien

    # ---- read ----
    def _serialize(self, b: JadwalBooking, nama: str, no_rm: str) -> dict:
        st = b.status_booking.value if hasattr(b.status_booking, "value") else str(b.status_booking or "")
        return {
            "id_booking": b.id_booking,
            "id_pasien": b.id_pasien,
            "nama_pasien": nama,
            "no_rm": no_rm,
            "tgl_rencana": b.tgl_rencana,
            "jam": b.jam_rencana.strftime("%H:%M") if b.jam_rencana else "",
            "jam_rencana": b.jam_rencana,
            "status": st,
            "id_staf_dokter_dituju": b.id_staf_dokter_dituju,
            "keluhan_utama": b.keluhan_utama,
            "catatan": b.catatan,
        }

    def list_bulan(self, tahun: int, bulan: int) -> dict:
        """Return {iso_date: [booking dict, ...]} untuk 1 bulan (order jam)."""
        first = date(tahun, bulan, 1)
        last = date(tahun + (bulan == 12), (bulan % 12) + 1, 1)  # first of next month (exclusive)
        rows = self.db.execute(
            select(JadwalBooking, Pasien.nama, Pasien.no_rm)
            .join(Pasien, Pasien.id_pasien == JadwalBooking.id_pasien)
            .where(JadwalBooking.tgl_rencana >= first)
            .where(JadwalBooking.tgl_rencana < last)
            .order_by(JadwalBooking.tgl_rencana, JadwalBooking.jam_rencana)
        ).all()
        out: dict = {}
        for b, nama, no_rm in rows:
            key = b.tgl_rencana.isoformat()
            out.setdefault(key, []).append(self._serialize(b, nama, no_rm))
        return out

    def list_tanggal(self, tgl) -> list:
        d = _norm_date(tgl)
        rows = self.db.execute(
            select(JadwalBooking, Pasien.nama, Pasien.no_rm)
            .join(Pasien, Pasien.id_pasien == JadwalBooking.id_pasien)
            .where(JadwalBooking.tgl_rencana == d)
            .order_by(JadwalBooking.jam_rencana)
        ).all()
        return [self._serialize(b, nama, no_rm) for b, nama, no_rm in rows]

    def list_members(self) -> list:
        """Daftar pasien member (VIP/VVIP) untuk dropdown New Booking."""
        rows = self.db.execute(
            select(Pasien)
            .where(Pasien.tipe_membership.in_([MembershipTierEnum.VIP, MembershipTierEnum.VVIP]))
            .order_by(Pasien.nama)
        ).scalars().all()
        return [
            {"id_pasien": p.id_pasien, "no_rm": p.no_rm, "nama": p.nama, "tier": _tier_of(p)}
            for p in rows
        ]

    def get(self, id_booking: int) -> JadwalBooking:
        b = self.db.get(JadwalBooking, id_booking)
        if b is None:
            raise HTTPException(404, f"Booking {id_booking} tidak ditemukan.")
        return b

    # ---- mutasi (FLUSH; caller commit) ----
    def create(self, id_pasien, tgl, jam, id_staf_dokter_dituju=None,
               keluhan_utama=None, catatan=None, actor_id_staf=None, request=None) -> JadwalBooking:
        self._get_pasien_membership(id_pasien)
        b = JadwalBooking(
            id_pasien=id_pasien,
            tgl_rencana=_norm_date(tgl),
            jam_rencana=_norm_time(jam),
            status_booking=StatusBookingEnum.BOOKED,
            sumber_pendaftaran="BOOKING",
            id_staf_dokter_dituju=id_staf_dokter_dituju or None,
            keluhan_utama=(keluhan_utama or "").strip() or None,
            catatan=(catatan or "").strip() or None,
            id_staf_input=actor_id_staf,
        )
        self.db.add(b)
        self.db.flush()
        self.audit.log_create(
            id_staf=actor_id_staf, tabel="jadwal_booking", id_target=b.id_booking,
            data_baru={"id_pasien": id_pasien, "tgl": str(b.tgl_rencana), "jam": b.jam_rencana.strftime("%H:%M")},
            request=request,
        )
        return b

    def edit(self, id_booking, tgl=None, jam=None, id_staf_dokter_dituju=..., keluhan_utama=None,
             catatan=None, actor_id_staf=None, request=None) -> JadwalBooking:
        b = self.get(id_booking)
        if b.status_booking in (StatusBookingEnum.CANCELLED, StatusBookingEnum.CHECKED_IN):
            raise HTTPException(400, "Booking yang sudah check-in / dibatalkan tak bisa diedit.")
        if tgl is not None:
            b.tgl_rencana = _norm_date(tgl)
        if jam is not None:
            b.jam_rencana = _norm_time(jam)
        if id_staf_dokter_dituju is not ...:
            b.id_staf_dokter_dituju = id_staf_dokter_dituju or None
        if keluhan_utama is not None:
            b.keluhan_utama = (keluhan_utama or "").strip() or None
        if catatan is not None:
            b.catatan = (catatan or "").strip() or None
        b.id_staf_input = actor_id_staf
        self.db.flush()
        self.audit.log(aksi="UPDATE", id_staf=actor_id_staf, tabel_target="jadwal_booking",
                       id_target=b.id_booking, keterangan="Edit booking", request=request)
        return b

    def confirm(self, id_booking, actor_id_staf=None, request=None) -> JadwalBooking:
        b = self.get(id_booking)
        if b.status_booking not in (StatusBookingEnum.BOOKED, StatusBookingEnum.RESCHEDULED):
            raise HTTPException(400, f"Hanya BOOKED/RESCHEDULED yang bisa dikonfirmasi (kini {b.status_booking}).")
        b.status_booking = StatusBookingEnum.CONFIRMED
        b.id_staf_input = actor_id_staf
        self.db.flush()
        self.audit.log(aksi="BOOKING_CONFIRM", id_staf=actor_id_staf, tabel_target="jadwal_booking",
                       id_target=b.id_booking, request=request)
        return b

    def cancel(self, id_booking, actor_id_staf=None, request=None) -> JadwalBooking:
        b = self.get(id_booking)
        if b.status_booking == StatusBookingEnum.CHECKED_IN:
            raise HTTPException(400, "Booking sudah check-in — tak bisa dibatalkan.")
        b.status_booking = StatusBookingEnum.CANCELLED
        b.id_staf_input = actor_id_staf
        self.db.flush()
        self.audit.log(aksi="BOOKING_CANCEL", id_staf=actor_id_staf, tabel_target="jadwal_booking",
                       id_target=b.id_booking, request=request)
        return b

    def reschedule(self, id_booking, tgl_baru, jam_baru, actor_id_staf=None, request=None) -> JadwalBooking:
        old = self.get(id_booking)
        if old.status_booking in (StatusBookingEnum.CANCELLED, StatusBookingEnum.CHECKED_IN):
            raise HTTPException(400, "Booking yang dibatalkan/check-in tak bisa di-reschedule.")
        old.status_booking = StatusBookingEnum.RESCHEDULED
        old.id_staf_input = actor_id_staf
        new = JadwalBooking(
            id_pasien=old.id_pasien,
            tgl_rencana=_norm_date(tgl_baru),
            jam_rencana=_norm_time(jam_baru),
            status_booking=StatusBookingEnum.BOOKED,
            sumber_pendaftaran="BOOKING",
            id_staf_dokter_dituju=old.id_staf_dokter_dituju,
            keluhan_utama=old.keluhan_utama,
            catatan=old.catatan,
            id_staf_input=actor_id_staf,
            id_booking_lama=old.id_booking,
        )
        self.db.add(new)
        self.db.flush()
        self.audit.log(aksi="BOOKING_RESCHEDULE", id_staf=actor_id_staf, tabel_target="jadwal_booking",
                       id_target=old.id_booking,
                       data_baru={"booking_baru": new.id_booking, "tgl": str(new.tgl_rencana)},
                       request=request)
        return new


    def check_in(self, id_booking, status_antrian, actor_id_staf=None, request=None) -> dict:
        """Check-in booking → buat Kunjungan hari ini (antrian), tandai CHECKED_IN.

        status_antrian: ANTRI_KONSULTASI (konsul) atau ANTRI_TREATMENT (tindakan/series).
        Memakai KunjunganService.kunjungan_lama (guard duplikat antrian + commit internal).
        Return dict hasil kunjungan_lama (berisi nomor_antrean).
        """
        from app.schemas.kunjungan import KunjunganLamaRequest
        from app.services.kunjungan_service import KunjunganService

        b = self.get(id_booking)
        if b.status_booking == StatusBookingEnum.CHECKED_IN:
            raise HTTPException(400, "Booking sudah check-in.")
        if b.status_booking == StatusBookingEnum.CANCELLED:
            raise HTTPException(400, "Booking sudah dibatalkan — tak bisa check-in.")
        if b.status_booking == StatusBookingEnum.RESCHEDULED:
            raise HTTPException(400, "Booking ini sudah dijadwal-ulang — check-in di jadwal barunya.")
        if status_antrian not in ("ANTRI_KONSULTASI", "ANTRI_TREATMENT"):
            raise HTTPException(400, "Tujuan antrian tidak valid (konsultasi / tindakan saja).")

        # Guard tanggal: check-in HANYA di hari-H booking (cegah masuk antrian lebih awal).
        hari_ini = date.today()
        if b.tgl_rencana != hari_ini:
            tgl_str = b.tgl_rencana.strftime("%d/%m/%Y")
            if b.tgl_rencana > hari_ini:
                raise HTTPException(
                    400,
                    f"Booking untuk {tgl_str} — belum bisa check-in hari ini. "
                    f"Check-in hanya di hari-H booking.",
                )
            raise HTTPException(
                400,
                f"Booking sudah lewat ({tgl_str}) — tak bisa check-in. "
                f"Jadwal-ulang dulu ke tanggal baru bila pasien tetap datang.",
            )

        # Re-assert gate member (jaga-jaga membership berubah sejak booking dibuat)
        self._get_pasien_membership(b.id_pasien)

        # Tandai CHECKED_IN dulu supaya ikut ter-commit bersama kunjungan_lama.
        b.status_booking = StatusBookingEnum.CHECKED_IN
        b.id_staf_input = actor_id_staf
        self.audit.log(
            aksi="BOOKING_CHECKIN", id_staf=actor_id_staf, tabel_target="jadwal_booking",
            id_target=b.id_booking, keterangan=f"Check-in → {status_antrian}", request=request,
        )
        payload = KunjunganLamaRequest(
            id_pasien=b.id_pasien,
            status_antrian=status_antrian,
            keluhan_utama=(b.keluhan_utama or ""),
            sumber_pendaftaran="BOOKING",
            antropometri=None,
            id_staf_dokter_assigned=b.id_staf_dokter_dituju,
        )
        # kunjungan_lama commit internal (booking + audit ikut ter-commit).
        return KunjunganService(self.db).kunjungan_lama(
            payload=payload, id_staf_fo=actor_id_staf, request=request,
        )


__all__ = ["BookingService", "MEMBERSHIP_TIERS"]
