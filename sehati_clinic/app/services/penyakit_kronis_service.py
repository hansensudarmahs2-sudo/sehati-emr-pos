"""
PenyakitKronisService — kosakata bersama penyakit kronis (master + kode).

Fondasi konektor AI + upgrade data Sehati. Ref CONTRACT_SEHATI_ANTROPOMETRI_v0.1.md §5/§6.
- list_master(): daftar master_penyakit_kronis (untuk checkbox UI).
- set_state(): reconcile penyakit kronis pasien dari STATE penuh (checkbox UI submit).
- apply_items(): reconcile dari item parsial (untuk write-back konektor, active flag eksplisit).
- backfill_kode(): best-effort map nama_penyakit free-text lama -> kode.

KODE 99 = "Lain-lain (free text)" — nama disimpan di pasien_penyakit_kronis.nama_penyakit.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MasterPenyakitKronis, PasienPenyakitKronis
from app.services.audit_service import AuditService

OTHER_KODE = 99

# Sinonim umum untuk backfill data lama (lowercase -> kode kanonik)
_SINONIM = {
    "dm": 1, "diabetes": 1, "diabetes melitus": 1, "diabetes mellitus": 1, "kencing manis": 1,
    "ht": 2, "hipertensi": 2, "darah tinggi": 2, "tekanan darah tinggi": 2,
    "jantung": 3, "penyakit jantung": 3, "sakit jantung": 3,
    "ginjal": 4, "penyakit ginjal": 4, "gagal ginjal": 4, "ckd": 4,
    "liver": 5, "hati": 5, "penyakit hati": 5, "hepatitis": 5,
    "asma": 6, "ppok": 6, "asthma": 6,
    "tiroid": 7, "hipertiroid": 7, "hipotiroid": 7, "gondok": 7,
    "stroke": 8,
    "eating disorder": 9, "gangguan makan": 9, "anoreksia": 9, "bulimia": 9,
    "ortopedi": 10, "ortopedik": 10, "sendi": 10, "osteoartritis": 10, "rematik": 10,
}


# =============================================================================
# PURE HELPER — diff state (testable tanpa DB)
# =============================================================================
def diff_state(existing, desired_codes, desired_others):
    """Hitung aksi reconcile dari STATE penuh.

    existing: list of dict {kode, nama, active} (baris pasien saat ini; kode bisa None).
    desired_codes: iterable int kode non-OTHER yang DICENTANG.
    desired_others: iterable str free-text OTHER yang diinginkan.

    Return dict {activate:set[kode], deactivate_codes:set[kode],
                 insert_codes:set[kode], insert_others:list[str], deactivate_others:list[str]}.
    """
    desired_codes = {int(k) for k in desired_codes if int(k) != OTHER_KODE}
    desired_others_norm = [o.strip() for o in desired_others if (o or "").strip()]
    desired_others_set = {o.lower() for o in desired_others_norm}

    active_codes = {r["kode"] for r in existing if r.get("active") and r.get("kode") not in (None, OTHER_KODE)}
    inactive_codes = {r["kode"] for r in existing if not r.get("active") and r.get("kode") not in (None, OTHER_KODE)}
    active_others = {(r.get("nama") or "").strip().lower() for r in existing if r.get("active") and r.get("kode") in (OTHER_KODE, None)}

    activate = {k for k in desired_codes if k in inactive_codes and k not in active_codes}
    insert_codes = {k for k in desired_codes if k not in active_codes and k not in inactive_codes}
    deactivate_codes = {k for k in active_codes if k not in desired_codes}

    insert_others = [o for o in desired_others_norm if o.lower() not in active_others]
    deactivate_others = [r["nama"] for r in existing
                         if r.get("active") and r.get("kode") in (OTHER_KODE, None)
                         and (r.get("nama") or "").strip().lower() not in desired_others_set]
    return {
        "activate": activate, "insert_codes": insert_codes,
        "deactivate_codes": deactivate_codes,
        "insert_others": insert_others, "deactivate_others": deactivate_others,
    }


class PenyakitKronisService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # ---- master ----
    def list_master(self, active_only: bool = True) -> list:
        stmt = select(MasterPenyakitKronis)
        if active_only:
            stmt = stmt.where(MasterPenyakitKronis.is_active.is_(True))
        stmt = stmt.order_by(MasterPenyakitKronis.urutan.asc(), MasterPenyakitKronis.kode.asc())
        return list(self.db.execute(stmt).scalars().all())

    def master_nama(self, kode: int) -> Optional[str]:
        row = self.db.get(MasterPenyakitKronis, kode)
        return row.nama if row else None

    def _existing_rows(self, id_pasien: int) -> list:
        rows = list(self.db.execute(
            select(PasienPenyakitKronis).where(PasienPenyakitKronis.id_pasien == id_pasien)
        ).scalars().all())
        return rows

    # ---- reconcile dari STATE penuh (UI checkbox) ----
    def set_state(self, id_pasien, checked_codes, others, actor_id_staf, request=None) -> dict:
        rows = self._existing_rows(id_pasien)
        existing = [{"kode": r.kode_penyakit, "nama": r.nama_penyakit, "active": bool(r.is_active)} for r in rows]
        plan = diff_state(existing, checked_codes, others)

        by_kode_active = {r.kode_penyakit: r for r in rows if r.is_active and r.kode_penyakit not in (None, OTHER_KODE)}
        by_kode_inactive = {r.kode_penyakit: r for r in rows if not r.is_active and r.kode_penyakit not in (None, OTHER_KODE)}
        applied = 0

        # activate (reuse baris inactive)
        for kode in plan["activate"]:
            r = by_kode_inactive.get(kode)
            if r is not None:
                r.is_active = True
                applied += 1
        # insert kode baru
        for kode in plan["insert_codes"]:
            nama = self.master_nama(kode) or f"Kode {kode}"
            self.db.add(PasienPenyakitKronis(
                id_pasien=id_pasien, kode_penyakit=kode, nama_penyakit=nama, is_active=True,
            ))
            applied += 1
        # deactivate kode tak dicentang
        for kode in plan["deactivate_codes"]:
            r = by_kode_active.get(kode)
            if r is not None:
                r.is_active = False
                applied += 1
        # OTHER: insert free-text baru
        for txt in plan["insert_others"]:
            self.db.add(PasienPenyakitKronis(
                id_pasien=id_pasien, kode_penyakit=OTHER_KODE, nama_penyakit=txt, is_active=True,
            ))
            applied += 1
        # OTHER: deactivate yang tak diinginkan
        deact_other_set = {t.strip().lower() for t in plan["deactivate_others"]}
        for r in rows:
            if r.is_active and r.kode_penyakit in (OTHER_KODE, None) and (r.nama_penyakit or "").strip().lower() in deact_other_set:
                r.is_active = False
                applied += 1

        self.audit.log(
            aksi="PENYAKIT_KRONIS_SYNC", id_staf=actor_id_staf,
            tabel_target="pasien_penyakit_kronis", id_target=id_pasien,
            data_baru={"checked_codes": sorted(plan["insert_codes"] | plan["activate"]),
                       "deactivated": sorted(plan["deactivate_codes"]),
                       "others_added": plan["insert_others"], "applied": applied},
            keterangan=f"Sync penyakit kronis pasien #{id_pasien} ({applied} perubahan)",
            request=request,
        )
        self.db.commit()
        return {"applied": applied}

    # ---- backfill data lama ----
    def backfill_kode(self, dry_run: bool = True) -> dict:
        rows = list(self.db.execute(
            select(PasienPenyakitKronis).where(PasienPenyakitKronis.kode_penyakit.is_(None))
        ).scalars().all())
        master = {m.nama.strip().lower(): m.kode for m in self.list_master(active_only=False)}
        matched = other = 0
        sample = []
        for r in rows:
            nm = (r.nama_penyakit or "").strip().lower()
            kode = master.get(nm) or _SINONIM.get(nm)
            if kode is None:
                # cek substring sinonim
                for key, kd in _SINONIM.items():
                    if key in nm:
                        kode = kd
                        break
            if kode is None:
                kode = OTHER_KODE
                other += 1
            else:
                matched += 1
            if len(sample) < 20:
                sample.append({"nama": r.nama_penyakit, "kode": kode})
            if not dry_run:
                r.kode_penyakit = kode
        if not dry_run:
            self.db.commit()
        return {"total": len(rows), "matched": matched, "other": other,
                "dry_run": dry_run, "sample": sample}


__all__ = ["PenyakitKronisService", "diff_state", "OTHER_KODE"]
