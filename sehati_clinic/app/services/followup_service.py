"""FollowupService — generation + workflow untuk modul reminder follow-up (#7).

Konsep (lihat Project_Memory/FOLLOWUP_REMINDER_DESIGN.md):
- Generation di-hook saat SOAP disimpan (= satu kali konsultasi dokter).
- SELALU buat 1 follow-up KONSULTASI per kunjungan
  (due = override dokter `tgl_kontrol_selanjutnya`, atau tgl_kunjungan + 1 minggu).
- Tiap item treatment (kunjungan_tindakan) → follow-up TREATMENT
  (due = tgl_kunjungan + `default_rentang_mulai_minggu`), KECUALI item konsultasi
  (dikenali dari nama, agar tidak dobel dengan follow-up KONSULTASI).
- Idempotent: upsert by (id_kunjungan, jenis, id_treatment); tidak menimpa baris
  yang sudah di-handle FO (status != PENDING).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Followup, Kunjungan, MasterTreatment, Pasien
from app.db.models._enums import JenisFollowupEnum, StatusFollowupEnum
from app.repositories.pemeriksaan_repo import PemeriksaanRepository

KONSULTASI_DEFAULT_MINGGU = 1

# Status yang masih perlu ditindak FO (muncul di worklist).
OPEN_STATUSES = (
    StatusFollowupEnum.PENDING,
    StatusFollowupEnum.NO_ANSWER,
    StatusFollowupEnum.RESCHEDULED,
)


def _is_konsultasi_treatment(nama: str | None) -> bool:
    """Heuristik: treatment yang namanya mengandung 'konsul' dianggap konsultasi."""
    return "konsul" in (nama or "").lower()


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


class FollowupService:
    def __init__(self, db: Session):
        self.db = db

    def _upsert(self, *, id_pasien, id_kunjungan, jenis, id_treatment, due_date, catatan):
        stmt = select(Followup).where(
            Followup.id_kunjungan == id_kunjungan,
            Followup.jenis == jenis,
        )
        if id_treatment is None:
            stmt = stmt.where(Followup.id_treatment.is_(None))
        else:
            stmt = stmt.where(Followup.id_treatment == id_treatment)
        existing = self.db.execute(stmt).scalars().first()

        if existing is not None:
            # Jangan clobber pekerjaan FO (status sudah bergerak dari PENDING).
            if existing.status == StatusFollowupEnum.PENDING:
                existing.due_date = due_date
                if catatan is not None:
                    existing.catatan = catatan
            return existing

        row = Followup(
            id_pasien=id_pasien,
            id_kunjungan=id_kunjungan,
            id_treatment=id_treatment,
            jenis=jenis,
            due_date=due_date,
            status=StatusFollowupEnum.PENDING,
            catatan=catatan,
        )
        self.db.add(row)
        return row

    def generate_for_kunjungan(self, id_kunjungan: int, commit: bool = True) -> int:
        """Buat/refresh follow-up untuk 1 kunjungan. Return jumlah follow-up disentuh."""
        kj = self.db.get(Kunjungan, id_kunjungan)
        if kj is None:
            return 0

        base_date = _as_date(kj.tgl_kunjungan)
        id_pasien = kj.id_pasien
        touched = 0

        # 1) KONSULTASI — selalu, satu per kunjungan.
        konsul_due = kj.tgl_kontrol_selanjutnya or (
            base_date + timedelta(weeks=KONSULTASI_DEFAULT_MINGGU)
        )
        self._upsert(
            id_pasien=id_pasien, id_kunjungan=id_kunjungan,
            jenis=JenisFollowupEnum.KONSULTASI, id_treatment=None,
            due_date=konsul_due, catatan=kj.catatan_kontrol,
        )
        touched += 1

        # 2) TREATMENT — per item, kecuali item konsultasi.
        repo = PemeriksaanRepository(self.db)
        seen_treatments: set[int] = set()
        for _tindakan, treatment in repo.get_tindakan_by_kunjungan(id_kunjungan):
            if _is_konsultasi_treatment(treatment.nama_treatment):
                continue
            if treatment.id_treatment in seen_treatments:
                continue
            minggu = treatment.default_rentang_mulai_minggu or 0
            if minggu <= 0:
                continue
            seen_treatments.add(treatment.id_treatment)
            self._upsert(
                id_pasien=id_pasien, id_kunjungan=id_kunjungan,
                jenis=JenisFollowupEnum.TREATMENT, id_treatment=treatment.id_treatment,
                due_date=base_date + timedelta(weeks=int(minggu)), catatan=None,
            )
            touched += 1

        if commit:
            self.db.commit()
        return touched


    # =====================================================================
    # G4 — Worklist + aksi (dipakai halaman Follow-up)
    # =====================================================================
    @staticmethod
    def _val(x):
        return x.value if hasattr(x, "value") else str(x)

    def list_due(self, start: date, end: date, *, only_open: bool = True) -> list[dict]:
        """Follow-up dengan due_date dalam [start, end]. Default hanya yang masih open."""
        stmt = (
            select(Followup, Pasien, MasterTreatment)
            .join(Pasien, Followup.id_pasien == Pasien.id_pasien)
            .outerjoin(MasterTreatment, Followup.id_treatment == MasterTreatment.id_treatment)
            .where(Followup.due_date >= start, Followup.due_date <= end)
            .order_by(Followup.due_date.asc(), Pasien.nama.asc())
        )
        if only_open:
            stmt = stmt.where(Followup.status.in_(OPEN_STATUSES))
        today = date.today()
        out: list[dict] = []
        for fu, pasien, treatment in self.db.execute(stmt).all():
            out.append({
                "id_followup": fu.id_followup,
                "id_pasien": fu.id_pasien,
                "id_kunjungan": fu.id_kunjungan,
                "due_date": fu.due_date,
                "jenis": self._val(fu.jenis),
                "nama_layanan": treatment.nama_treatment if treatment else "Konsultasi",
                "status": self._val(fu.status),
                "catatan": fu.catatan or "",
                "no_rm": pasien.no_rm,
                "nama_pasien": pasien.nama,
                "nomor_telepon": pasien.nomor_telepon or "",
                "overdue": fu.due_date < today,
            })
        return out

    def counts_open(self, start: date, end: date) -> dict:
        """Ringkasan cepat untuk header halaman."""
        items = self.list_due(start, end, only_open=True)
        today = date.today()
        return {
            "total": len(items),
            "overdue": sum(1 for i in items if i["due_date"] < today),
            "hari_ini": sum(1 for i in items if i["due_date"] == today),
        }

    def _apply_action(self, id_followup, new_status, id_staf, *, catatan=None, new_due=None, commit=True):
        fu = self.db.get(Followup, id_followup)
        if fu is None:
            return None
        fu.status = new_status
        fu.id_staf_handler = id_staf
        fu.waktu_handle = datetime.now()
        if catatan is not None:
            fu.catatan = catatan
        if new_due is not None:
            fu.due_date = new_due
        if commit:
            self.db.commit()
        return fu

    def confirm(self, id_followup, id_staf, catatan=None):
        return self._apply_action(id_followup, StatusFollowupEnum.CONFIRMED, id_staf, catatan=catatan)

    def no_answer(self, id_followup, id_staf, catatan=None):
        return self._apply_action(id_followup, StatusFollowupEnum.NO_ANSWER, id_staf, catatan=catatan)

    def cancel(self, id_followup, id_staf, catatan=None):
        return self._apply_action(id_followup, StatusFollowupEnum.CANCELLED, id_staf, catatan=catatan)

    def reschedule(self, id_followup, id_staf, new_due: date, catatan=None):
        return self._apply_action(id_followup, StatusFollowupEnum.RESCHEDULED, id_staf, catatan=catatan, new_due=new_due)
