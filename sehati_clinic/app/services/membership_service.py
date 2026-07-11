"""
MembershipService — full membership lifecycle.

Pattern:
- pasien_membership_history.is_active=False, id_transaksi_aktivasi=NULL = PENDING (menunggu bayar)
- is_active=True, id_transaksi_aktivasi NOT NULL = ACTIVE (sudah bayar, dalam periode)
- is_active=False, id_transaksi_aktivasi NOT NULL = EXPIRED/CANCELLED

Lifecycle methods (#362E):
- get_status_pasien — current state + active history + pending history
- create_pending_activation — pasien REGULAR mau jadi VIP/VVIP
- create_pending_renewal — extend tier yang sama, expired/nearing expire
- create_pending_upgrade — VIP → VVIP
- cancel_pending_history — batalkan pending yang belum dibayar
- revert_active_to_pending — saat void transaksi yang mengandung aktivasi
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple, Optional

from fastapi import HTTPException, Request, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MasterMembership, Pasien, PasienMembershipHistory
from app.services.audit_service import AuditService


class DiskonMembership(NamedTuple):
    """Tuple diskon per pasien — persen treatment & produk."""
    persen_treatment: Decimal
    persen_produk: Decimal
    nama_tier: str
    found: bool  # True = tier dapat di master_membership; False = fallback ke 0


class MembershipService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # =========================================================================
    # READ
    # =========================================================================
    def get_diskon_for_pasien(self, id_pasien: int) -> DiskonMembership:
        """Lookup diskon berdasarkan tier pasien + ACTIVE history."""
        pasien = self.db.get(Pasien, id_pasien)
        if pasien is None:
            return DiskonMembership(Decimal("0"), Decimal("0"), "UNKNOWN", False)

        tier_value = (
            pasien.tipe_membership.value
            if hasattr(pasien.tipe_membership, "value")
            else str(pasien.tipe_membership) if pasien.tipe_membership else "REGULAR"
        )

        if tier_value.upper() == "REGULAR":
            return DiskonMembership(Decimal("0"), Decimal("0"), tier_value, False)

        stmt = (
            select(MasterMembership)
            .where(MasterMembership.nama_tier == tier_value)
            .where(MasterMembership.is_active.is_(True))
            .limit(1)
        )
        tier = self.db.execute(stmt).scalar_one_or_none()
        if tier is None:
            return DiskonMembership(Decimal("0"), Decimal("0"), tier_value, False)

        # #362D - Require ACTIVE history (sudah dibayar)
        active_hist_stmt = (
            select(PasienMembershipHistory)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.id_membership == tier.id_membership)
            .where(PasienMembershipHistory.is_active.is_(True))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
            .where(PasienMembershipHistory.tgl_expired >= date.today())
            .limit(1)
        )
        active_hist = self.db.execute(active_hist_stmt).scalar_one_or_none()
        if active_hist is None:
            return DiskonMembership(Decimal("0"), Decimal("0"), tier_value, False)

        return DiskonMembership(
            persen_treatment=Decimal(str(tier.diskon_treatment_persen or 0)),
            persen_produk=Decimal(str(tier.diskon_produk_persen or 0)),
            nama_tier=tier.nama_tier,
            found=True,
        )

    def get_status_pasien(self, id_pasien: int) -> dict:
        """Return current membership state untuk display di section Membership."""
        pasien = self.db.get(Pasien, id_pasien)
        if pasien is None:
            raise HTTPException(404, f"Pasien {id_pasien} tidak ditemukan.")

        # Current tier dari pasien.tipe_membership (informational)
        tier_value = (
            pasien.tipe_membership.value
            if hasattr(pasien.tipe_membership, "value")
            else str(pasien.tipe_membership) if pasien.tipe_membership else "REGULAR"
        )

        # Active history
        today = date.today()
        active_hist = self.db.execute(
            select(PasienMembershipHistory, MasterMembership)
            .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(True))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
            .where(PasienMembershipHistory.tgl_expired >= today)
            .order_by(PasienMembershipHistory.tgl_aktif.desc())
            .limit(1)
        ).first()

        # Pending history
        pending_hist = self.db.execute(
            select(PasienMembershipHistory, MasterMembership)
            .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(False))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_(None))
            .order_by(PasienMembershipHistory.id_history.desc())
            .limit(1)
        ).first()

        # All history (for display)
        all_history = list(self.db.execute(
            select(PasienMembershipHistory, MasterMembership)
            .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .order_by(PasienMembershipHistory.id_history.desc())
            .limit(20)
        ).all())

        # Active tiers (untuk dropdown aktivasi/upgrade)
        active_tiers = list(self.db.execute(
            select(MasterMembership)
            .where(MasterMembership.is_active.is_(True))
            .where(MasterMembership.nama_tier != "REGULAR")
            .order_by(MasterMembership.urutan_tampilan.asc())
        ).scalars().all())

        days_to_expire = None
        if active_hist:
            hist_row, tier_row = active_hist
            days_to_expire = (hist_row.tgl_expired - today).days

        # #362B-D - Cek existing kunjungan ANTRI_BAYAR membership-only untuk hide button
        from app.db.models import Kunjungan as _K
        existing_billing = self.db.execute(
            select(_K)
            .where(_K.id_pasien == id_pasien)
            .where(_K.status_antrian == "ANTRI_BAYAR")
            .where(_K.sumber_pendaftaran == "MEMBERSHIP_ONLY")
            .order_by(_K.id_kunjungan.desc())
            .limit(1)
        ).scalar_one_or_none()
        existing_billing_kunjungan_id = existing_billing.id_kunjungan if existing_billing else None

        return {
            "pasien": {
                "id_pasien": pasien.id_pasien,
                "no_rm": pasien.no_rm,
                "nama": pasien.nama,
                "tipe_membership": tier_value,
            },
            "existing_billing_kunjungan_id": existing_billing_kunjungan_id,
            "active": {
                "id_history": active_hist[0].id_history if active_hist else None,
                "id_membership": active_hist[0].id_membership if active_hist else None,
                "nama_tier": active_hist[1].nama_tier if active_hist else None,
                "tgl_aktif": active_hist[0].tgl_aktif if active_hist else None,
                "tgl_expired": active_hist[0].tgl_expired if active_hist else None,
                "harga_bayar": float(active_hist[0].harga_bayar) if active_hist else 0,
                "id_transaksi_aktivasi": active_hist[0].id_transaksi_aktivasi if active_hist else None,
                "days_to_expire": days_to_expire,
            } if active_hist else None,
            "pending": {
                "id_history": pending_hist[0].id_history if pending_hist else None,
                "id_membership": pending_hist[0].id_membership if pending_hist else None,
                "nama_tier": pending_hist[1].nama_tier if pending_hist else None,
                "harga_bayar": float(pending_hist[0].harga_bayar) if pending_hist else 0,
                "catatan": pending_hist[0].catatan if pending_hist else None,
            } if pending_hist else None,
            "history_list": [
                {
                    "id_history": h.id_history,
                    "nama_tier": m.nama_tier,
                    "tgl_aktif": h.tgl_aktif,
                    "tgl_expired": h.tgl_expired,
                    "harga_bayar": float(h.harga_bayar),
                    "id_transaksi_aktivasi": h.id_transaksi_aktivasi,
                    "is_active": h.is_active,
                    "catatan": h.catatan,
                    "status_label": (
                        "ACTIVE" if h.is_active and h.id_transaksi_aktivasi
                        else "PENDING" if not h.is_active and h.id_transaksi_aktivasi is None
                        else "EXPIRED/CANCELLED"
                    ),
                }
                for h, m in all_history
            ],
            "available_tiers": [
                {
                    "id_membership": t.id_membership,
                    "nama_tier": t.nama_tier,
                    "harga_aktivasi": float(t.harga_aktivasi or 0),
                    "durasi_bulan": int(t.durasi_bulan or 0),
                    "diskon_treatment_persen": float(t.diskon_treatment_persen or 0),
                    "diskon_produk_persen": float(t.diskon_produk_persen or 0),
                }
                for t in active_tiers
            ],
            # P2-#2 - Kuota usage breakdown untuk display
            "kuota_list": self.list_kuota_for_pasien(id_pasien) if active_hist else [],
        }

    # =========================================================================
    # LIFECYCLE ACTIONS
    # =========================================================================
    def create_pending(
        self,
        id_pasien: int,
        id_membership: int,
        actor_id_staf: int,
        action_type: str = "ACTIVATION",  # ACTIVATION | RENEWAL | UPGRADE
        request: Optional[Request] = None,
    ) -> PasienMembershipHistory:
        """Generic create pending history (handles activation/renewal/upgrade)."""
        pasien = self.db.get(Pasien, id_pasien)
        if pasien is None:
            raise HTTPException(404, f"Pasien {id_pasien} tidak ditemukan.")

        tier = self.db.get(MasterMembership, id_membership)
        if tier is None or not tier.is_active:
            raise HTTPException(400, "Tier tidak ditemukan atau tidak aktif.")
        if tier.nama_tier.upper() == "REGULAR":
            raise HTTPException(400, "Tidak perlu aktivasi untuk REGULAR.")

        # Cek tidak ada pending lain yang belum dibayar
        existing_pending = self.db.execute(
            select(PasienMembershipHistory)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(False))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_(None))
            .limit(1)
        ).scalar_one_or_none()
        if existing_pending is not None:
            raise HTTPException(
                409,
                "Sudah ada pending membership yang belum dibayar. "
                "Bayar atau cancel dulu sebelum buat yang baru.",
            )

        # Validate action vs current state
        active_now = self.db.execute(
            select(PasienMembershipHistory)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(True))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
            .where(PasienMembershipHistory.tgl_expired >= date.today())
            .limit(1)
        ).scalar_one_or_none()

        action_upper = action_type.upper()
        if action_upper == "ACTIVATION" and active_now is not None:
            raise HTTPException(
                400,
                "Pasien sudah punya membership aktif. Gunakan RENEWAL atau UPGRADE.",
            )
        if action_upper in ("RENEWAL", "UPGRADE") and active_now is None:
            raise HTTPException(
                400,
                f"Tidak ada membership aktif untuk di-{action_upper}. Gunakan ACTIVATION.",
            )

        today = date.today()
        # #362F - Carry-over untuk RENEWAL (extend dari current expired)
        # #362B-A - Preserve tgl_aktif original supaya display "Aktif sejak X → Expired Y" intuitif
        # UPGRADE/ACTIVATION tetap reset (start fresh)
        durasi_days = int(tier.durasi_bulan or 12) * 30
        if action_upper == "RENEWAL" and active_now is not None:
            # Extend dari current.tgl_expired (kalau masih aktif)
            base_date = max(active_now.tgl_expired, today)
            tgl_expired_baru = base_date + timedelta(days=durasi_days)
            tgl_aktif_baru = active_now.tgl_aktif  # PRESERVE original start
            catatan_extra = (
                f"Carry-over RENEWAL: tgl_aktif preserved {active_now.tgl_aktif}, "
                f"sisa {(active_now.tgl_expired - today).days} hari "
                f"+ {durasi_days} hari = total expired {tgl_expired_baru}"
            )
        else:
            tgl_expired_baru = today + timedelta(days=durasi_days)
            tgl_aktif_baru = today
            catatan_extra = ""

        history = PasienMembershipHistory(
            id_pasien=id_pasien,
            id_membership=id_membership,
            tgl_aktif=tgl_aktif_baru,
            tgl_expired=tgl_expired_baru,
            harga_bayar=float(tier.harga_aktivasi or 0),
            id_transaksi_aktivasi=None,
            id_staf_aktivasi=None,
            is_active=False,
            catatan=(
                f"PENDING {action_upper} - {tier.nama_tier}"
                + (f". {catatan_extra}" if catatan_extra else "")
            ),
        )
        self.db.add(history)
        self.db.flush()

        # FIX-362E-A: JANGAN update pasien.tipe_membership di sini.
        # Hanya update saat proses_bayar trigger aktivasi (tier baru efektif).
        # Display di Cari Pasien/Antrian Kasir tetap tampilkan tier LAMA sampai dibayar.

        try:
            self.audit.log_create(
                id_staf=actor_id_staf,
                tabel="pasien_membership_history",
                id_target=history.id_history,
                data_baru={
                    "id_pasien": id_pasien,
                    "id_membership": id_membership,
                    "nama_tier": tier.nama_tier,
                    "harga_bayar": float(tier.harga_aktivasi or 0),
                    "action_type": action_upper,
                    "status": "PENDING",
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(history)
            return history
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal create pending: {e!s}")

    def cancel_pending(
        self,
        id_history: int,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """Cancel pending history yang belum dibayar."""
        hist = self.db.get(PasienMembershipHistory, id_history)
        if hist is None:
            raise HTTPException(404, "Pending history tidak ditemukan.")
        if hist.is_active or hist.id_transaksi_aktivasi is not None:
            raise HTTPException(400, "History sudah ACTIVE/EXPIRED, tidak bisa di-cancel.")

        try:
            id_pasien = hist.id_pasien
            data_lama = {
                "id_pasien": id_pasien,
                "id_membership": hist.id_membership,
                "status": "PENDING",
            }
            self.db.delete(hist)
            # FIX-362E-C: Revert pasien.tipe_membership ke active history tier (atau REGULAR)
            # supaya consistent kalau Cancel UPGRADE yang sebelumnya update tipe_membership
            prev_active = self.db.execute(
                select(PasienMembershipHistory, MasterMembership)
                .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
                .where(PasienMembershipHistory.id_pasien == id_pasien)
                .where(PasienMembershipHistory.is_active.is_(True))
                .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
                .where(PasienMembershipHistory.tgl_expired >= date.today())
                .order_by(PasienMembershipHistory.tgl_aktif.desc())
                .limit(1)
            ).first()
            from app.db.models import MembershipTierEnum
            pasien_rev = self.db.get(Pasien, id_pasien)
            if pasien_rev is not None:
                target_tier = prev_active[1].nama_tier if prev_active else "REGULAR"
                try:
                    pasien_rev.tipe_membership = MembershipTierEnum(target_tier)
                except ValueError:
                    pass
            self.audit.log_delete(
                id_staf=actor_id_staf,
                tabel="pasien_membership_history",
                id_target=id_history,
                data_lama=data_lama,
                request=request,
            )
            self.db.commit()
            return {"status": "success", "id_history": id_history, "id_pasien": id_pasien}
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal cancel pending: {e!s}")

    def revert_active_to_pending(
        self,
        id_transaksi: int,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> Optional[int]:
        """Saat void transaksi yang mengandung aktivasi - revert history ke PENDING.

        Returns id_history yang di-revert, atau None kalau tidak ada.
        Dipanggil dari kasir_service.void_transaksi.
        """
        hist = self.db.execute(
            select(PasienMembershipHistory)
            .where(PasienMembershipHistory.id_transaksi_aktivasi == id_transaksi)
            .where(PasienMembershipHistory.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if hist is None:
            return None

        try:
            # Deactivate associated kuota rows
            from app.db.models import PasienMembershipKuota
            kuotas = list(self.db.execute(
                select(PasienMembershipKuota)
                .where(PasienMembershipKuota.id_membership_history == hist.id_history)
            ).scalars().all())
            for k in kuotas:
                k.is_active = False

            # Revert history ke PENDING
            id_hist = hist.id_history
            id_pasien_for_revert = hist.id_pasien
            hist.is_active = False
            hist.id_transaksi_aktivasi = None
            hist.id_staf_aktivasi = None
            hist.catatan = (
                f"REVERTED TO PENDING - transaksi #{id_transaksi} di-void. "
                f"Catatan lama: {hist.catatan or ''}"
            )
            # FIX-362E-A: Revert pasien.tipe_membership ke tier OTHER active history (kalau ada),
            # atau REGULAR (kalau tidak ada history active lain)
            prev_active = self.db.execute(
                select(PasienMembershipHistory, MasterMembership)
                .join(MasterMembership, MasterMembership.id_membership == PasienMembershipHistory.id_membership)
                .where(PasienMembershipHistory.id_pasien == id_pasien_for_revert)
                .where(PasienMembershipHistory.id_history != id_hist)
                .where(PasienMembershipHistory.is_active.is_(True))
                .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
                .where(PasienMembershipHistory.tgl_expired >= date.today())
                .order_by(PasienMembershipHistory.tgl_aktif.desc())
                .limit(1)
            ).first()
            from app.db.models import MembershipTierEnum
            pasien_rev = self.db.get(Pasien, id_pasien_for_revert)
            if pasien_rev is not None:
                target_tier = prev_active[1].nama_tier if prev_active else "REGULAR"
                try:
                    pasien_rev.tipe_membership = MembershipTierEnum(target_tier)
                except ValueError:
                    pass
            self.db.flush()
            self.audit.log(
                aksi="MEMBERSHIP_REVERT_PENDING",
                id_staf=actor_id_staf,
                tabel_target="pasien_membership_history",
                id_target=id_hist,
                data_lama={"is_active": True, "id_transaksi_aktivasi": id_transaksi},
                data_baru={"is_active": False, "id_transaksi_aktivasi": None},
                keterangan=(
                    f"Revert ke PENDING karena transaksi #{id_transaksi} di-void. "
                    f"Kuota auto-deactivated: {len(kuotas)} rows."
                ),
                request=request,
            )
            return id_hist
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal revert membership history: {e!s}")


    # =========================================================================
    # FIX-362E-B: Standalone billing flow (kunjungan membership-only)
    # =========================================================================
    def create_kunjungan_billing(
        self,
        id_pasien: int,
        actor_id_staf: int,
        request=None,
    ) -> int:
        """Buat kunjungan minimal status ANTRI_BAYAR untuk pasien dengan pending membership.

        Use case: pasien existing yang upgrade/renew membership langsung,
        tanpa flow konsul. Bayar via kasir langsung.

        Returns: id_kunjungan baru.
        """
        from app.db.models import Kunjungan, Pasien
        from app.repositories.kunjungan_repo import KunjunganRepository

        pasien = self.db.get(Pasien, id_pasien)
        if pasien is None:
            raise HTTPException(404, f"Pasien {id_pasien} tidak ditemukan.")

        # Cek ada pending history dulu, kalau tidak ada tidak perlu billing
        pending = self.db.execute(
            select(PasienMembershipHistory)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(False))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_(None))
            .limit(1)
        ).scalar_one_or_none()
        if pending is None:
            raise HTTPException(
                400,
                "Tidak ada pending membership. Buat pending dulu via Aktivasi/Perpanjang/Upgrade.",
            )

        # FIX-362E-D: Block duplicate billing — check existing ANTRI_BAYAR membership-only kunjungan
        from app.db.models import Kunjungan as _K
        from sqlalchemy import or_ as _or
        existing_billing = self.db.execute(
            select(_K)
            .where(_K.id_pasien == id_pasien)
            .where(_K.status_antrian == "ANTRI_BAYAR")
            .where(_K.sumber_pendaftaran == "MEMBERSHIP_ONLY")
            .limit(1)
        ).scalar_one_or_none()
        if existing_billing is not None:
            raise HTTPException(
                409,
                f"Sudah ada kunjungan billing membership #{existing_billing.id_kunjungan} "
                f"dengan status ANTRI_BAYAR. Selesaikan dulu atau void kalau tidak terpakai.",
            )

        try:
            kunjungan_repo = KunjunganRepository(self.db)
            nomor_antrean = kunjungan_repo.get_nomor_antrian_berikutnya()
            kunjungan = Kunjungan(
                id_pasien=id_pasien,
                status_antrian="ANTRI_BAYAR",
                keluhan_utama="Aktivasi membership (no consultation)",
                id_staf_fo=actor_id_staf,
                nomor_antrean=nomor_antrean,
                sumber_pendaftaran="MEMBERSHIP_ONLY",
            )
            kunjungan_repo.create(kunjungan)
            self.audit.log_create(
                id_staf=actor_id_staf,
                tabel="kunjungan",
                id_target=kunjungan.id_kunjungan,
                data_baru={
                    "id_pasien": id_pasien,
                    "status_antrian": "ANTRI_BAYAR",
                    "sumber_pendaftaran": "MEMBERSHIP_ONLY",
                    "purpose": f"Bayar pending {pending.id_history}",
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(kunjungan)
            return kunjungan.id_kunjungan
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal buat kunjungan billing: {e!s}")


    # =========================================================================
    # P2-#1 — Kuota helpers (lazy-create + sisa lookup)
    # =========================================================================
    def get_or_create_kuota_for_treatment(
        self,
        id_pasien: int,
        id_treatment: int,
        target_date: Optional[date] = None,
    ):
        """P2-#1 — Lookup kuota tersedia untuk treatment pada pasien.

        Untuk TOTAL_PAKET: cek row existing (sudah dibuat saat aktivasi).
        Untuk BULANAN: lazy-create row untuk bulan target (default = today).

        Return: dict {id_kuota, kuota_total, kuota_terpakai, sisa, periode_kuota, expired_at}
                atau None kalau tidak ada benefit / membership tidak aktif.
        """
        from app.db.models import (
            MasterMembership as _MM,
            MasterMembershipBenefitTreatment as _MMBT,
            PasienMembershipKuota as _PMK,
            PeriodeKuotaEnum as _PKE,
        )

        if target_date is None:
            target_date = date.today()

        # Step 1: cek active membership history
        active_hist = self.db.execute(
            select(PasienMembershipHistory, _MM)
            .join(_MM, _MM.id_membership == PasienMembershipHistory.id_membership)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(True))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
            .where(PasienMembershipHistory.tgl_expired >= target_date)
            .order_by(PasienMembershipHistory.tgl_aktif.desc())
            .limit(1)
        ).first()

        if active_hist is None:
            return None

        hist, tier = active_hist

        # Step 2: cek benefit config untuk treatment ini
        benefit = self.db.execute(
            select(_MMBT)
            .where(_MMBT.id_membership == tier.id_membership)
            .where(_MMBT.id_treatment == id_treatment)
            .where(_MMBT.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()

        if benefit is None:
            return None

        periode_val = (
            benefit.periode_kuota.value
            if hasattr(benefit.periode_kuota, "value")
            else str(benefit.periode_kuota)
        )

        # Step 3: cari kuota row
        bulan_str = target_date.strftime("%Y-%m") if periode_val == "BULANAN" else None
        stmt = (
            select(_PMK)
            .where(_PMK.id_pasien == id_pasien)
            .where(_PMK.id_treatment == id_treatment)
            .where(_PMK.id_membership_history == hist.id_history)
            .where(_PMK.is_active.is_(True))
            .where(_PMK.periode_kuota == benefit.periode_kuota)
        )
        if periode_val == "BULANAN":
            stmt = stmt.where(_PMK.bulan_periode == bulan_str)
        else:
            stmt = stmt.where(_PMK.bulan_periode.is_(None))
        stmt = stmt.limit(1)
        kuota_row = self.db.execute(stmt).scalar_one_or_none()

        # Step 4: Lazy-create kalau row belum ada
        # BULANAN: row baru per bulan (sesuai design lazy-create)
        # TOTAL_PAKET: fallback lazy-create kalau benefit ditambah AFTER aktivasi
        #              (kasus: owner add benefit baru tengah jalan, atau membership
        #              di-aktifkan sebelum auto-create logic deployed)
        if kuota_row is None:
            # A3 (DEC-081): lazy-create di SAVEPOINT (begin_nested) — kalau insert gagal,
            # hanya savepoint ini yang di-rollback; transaksi INDUK (simpan pemeriksaan)
            # tetap utuh. JANGAN db.rollback() session bersama di dalam helper.
            try:
                with self.db.begin_nested():
                    new_kuota = _PMK(
                        id_pasien=id_pasien,
                        id_membership_history=hist.id_history,
                        id_treatment=id_treatment,
                        periode_kuota=benefit.periode_kuota,
                        bulan_periode=bulan_str,  # None untuk TOTAL_PAKET
                        kuota_total=int(benefit.kuota_total or 0),
                        kuota_terpakai=0,
                        is_active=True,
                        expired_at=hist.tgl_expired,
                    )
                    self.db.add(new_kuota)
                    self.db.flush()
                kuota_row = new_kuota
            except Exception:
                # SAVEPOINT sudah di-rollback otomatis; transaksi induk aman.
                return None

        if kuota_row is None:
            return None

        sisa = max(0, int(kuota_row.kuota_total or 0) - int(kuota_row.kuota_terpakai or 0))
        return {
            "id_kuota": kuota_row.id_kuota,
            "kuota_total": int(kuota_row.kuota_total or 0),
            "kuota_terpakai": int(kuota_row.kuota_terpakai or 0),
            "sisa": sisa,
            "periode_kuota": periode_val,
            "bulan_periode": kuota_row.bulan_periode,
            "expired_at": kuota_row.expired_at,
            "id_history": hist.id_history,
            "nama_tier": tier.nama_tier,
        }

    def _kuota_audit_keterangan(self, kuota, prefix: str, id_kunjungan=None, id_tindakan=None) -> str:
        """LOG-1 helper — build human-readable keterangan untuk audit kuota.

        Joins kuota row -> treatment + tier + periode info. Best-effort,
        gagal join akan fallback ke minimal info.
        """
        from app.db.models import (
            MasterTreatment as _MT,
            MasterMembership as _MM,
            PasienMembershipHistory as _PMH,
        )
        nama_treatment = "?"
        nama_tier = "?"
        harga_nominal = 0
        try:
            t = self.db.get(_MT, kuota.id_treatment) if kuota.id_treatment else None
            if t is not None:
                nama_treatment = t.nama_treatment
                harga_nominal = int(float(t.harga or 0))
        except Exception:
            pass
        try:
            hist = self.db.get(_PMH, kuota.id_membership_history) if kuota.id_membership_history else None
            if hist is not None:
                tier = self.db.get(_MM, hist.id_membership)
                if tier is not None:
                    nama_tier = tier.nama_tier
        except Exception:
            pass

        periode_val = (
            kuota.periode_kuota.value if hasattr(kuota.periode_kuota, "value")
            else str(kuota.periode_kuota or "?")
        )
        bulan_str = (f" {kuota.bulan_periode}" if kuota.bulan_periode else "")
        sisa = max(0, int(kuota.kuota_total or 0) - int(kuota.kuota_terpakai or 0))

        parts = [
            f"{prefix} \"{nama_treatment}\" ({nama_tier} {periode_val}{bulan_str}).",
            f"Sisa: {sisa}/{int(kuota.kuota_total or 0)}.",
        ]
        if id_kunjungan is not None:
            parts.append(f"Kunjungan #{id_kunjungan}.")
        if id_tindakan is not None:
            parts.append(f"Tindakan #{id_tindakan}.")
        if harga_nominal > 0:
            parts.append(f"Nominal diskon: Rp {harga_nominal:,}".replace(",", "."))
        return " ".join(parts)

    def increment_kuota_terpakai(
        self,
        id_kuota: int,
        *,
        actor_id_staf=None,
        id_kunjungan=None,
        id_tindakan=None,
        request=None,
    ) -> bool:
        """Atomic increment kuota_terpakai. Return True kalau sukses (sisa > 0).

        LOG-1: Tulis audit KUOTA_PAKAI kalau actor_id_staf disediakan.
        Param actor_id_staf/id_kunjungan/id_tindakan/request optional supaya
        backward-compat dengan callsite lama.
        """
        from app.db.models import PasienMembershipKuota as _PMK
        kuota = self.db.get(_PMK, id_kuota)
        if kuota is None or not kuota.is_active:
            return False
        sisa = int(kuota.kuota_total or 0) - int(kuota.kuota_terpakai or 0)
        if sisa <= 0:
            return False
        terpakai_lama = int(kuota.kuota_terpakai or 0)
        kuota.kuota_terpakai = terpakai_lama + 1
        self.db.flush()

        # LOG-1: audit entry KUOTA_PAKAI (best-effort, jangan block bisnis)
        if actor_id_staf is not None:
            try:
                self.audit.log(
                    aksi="KUOTA_PAKAI",
                    id_staf=actor_id_staf,
                    tabel_target="pasien_membership_kuota",
                    id_target=id_kuota,
                    data_lama={"kuota_terpakai": terpakai_lama},
                    data_baru={"kuota_terpakai": terpakai_lama + 1},
                    keterangan=self._kuota_audit_keterangan(
                        kuota, prefix="Pakai kuota benefit",
                        id_kunjungan=id_kunjungan, id_tindakan=id_tindakan,
                    ),
                    request=request,
                )
            except Exception:
                pass
        return True

    def decrement_kuota_terpakai(
        self,
        id_kuota: int,
        *,
        actor_id_staf=None,
        id_kunjungan=None,
        id_tindakan=None,
        request=None,
    ) -> bool:
        """Revert kuota usage (saat void treatment). Floor at 0.

        LOG-1: Tulis audit KUOTA_REVERT kalau actor_id_staf disediakan.
        """
        from app.db.models import PasienMembershipKuota as _PMK
        kuota = self.db.get(_PMK, id_kuota)
        if kuota is None:
            return False
        terpakai_lama = int(kuota.kuota_terpakai or 0)
        kuota.kuota_terpakai = max(0, terpakai_lama - 1)
        self.db.flush()

        if actor_id_staf is not None:
            try:
                self.audit.log(
                aksi="KUOTA_REVERT",
                    id_staf=actor_id_staf,
                    tabel_target="pasien_membership_kuota",
                    id_target=id_kuota,
                    data_lama={"kuota_terpakai": terpakai_lama},
                    data_baru={"kuota_terpakai": kuota.kuota_terpakai},
                    keterangan=self._kuota_audit_keterangan(
                        kuota, prefix="Revert kuota benefit",
                        id_kunjungan=id_kunjungan, id_tindakan=id_tindakan,
                    ),
                    request=request,
                )
            except Exception:
                pass
        return True

    def list_kuota_for_pasien(self, id_pasien: int, target_date: Optional[date] = None) -> list[dict]:
        """P2-#2 helper — list semua kuota aktif pasien untuk display.

        TOTAL_PAKET: list semua row aktif.
        BULANAN: list semua benefit config kalau pasien punya active membership,
                 enriched dengan kuota_terpakai bulan ini (atau 0 kalau row belum dibuat).
        """
        from app.db.models import (
            MasterMembership as _MM,
            MasterMembershipBenefitTreatment as _MMBT,
            MasterTreatment as _MT,
            PasienMembershipKuota as _PMK,
            PeriodeKuotaEnum as _PKE,
        )

        if target_date is None:
            target_date = date.today()
        bulan_str = target_date.strftime("%Y-%m")

        # Active history pasien
        active_hist = self.db.execute(
            select(PasienMembershipHistory, _MM)
            .join(_MM, _MM.id_membership == PasienMembershipHistory.id_membership)
            .where(PasienMembershipHistory.id_pasien == id_pasien)
            .where(PasienMembershipHistory.is_active.is_(True))
            .where(PasienMembershipHistory.id_transaksi_aktivasi.is_not(None))
            .where(PasienMembershipHistory.tgl_expired >= target_date)
            .order_by(PasienMembershipHistory.tgl_aktif.desc())
            .limit(1)
        ).first()

        if active_hist is None:
            return []

        hist, tier = active_hist

        # Semua benefit config untuk tier ini
        benefits = list(self.db.execute(
            select(_MMBT, _MT)
            .join(_MT, _MT.id_treatment == _MMBT.id_treatment)
            .where(_MMBT.id_membership == tier.id_membership)
            .where(_MMBT.is_active.is_(True))
            .order_by(_MT.nama_treatment.asc())
        ).all())

        result = []
        for b, t in benefits:
            periode_val = (
                b.periode_kuota.value if hasattr(b.periode_kuota, "value")
                else str(b.periode_kuota)
            )
            # Lookup existing kuota row
            stmt = (
                select(_PMK)
                .where(_PMK.id_pasien == id_pasien)
                .where(_PMK.id_treatment == b.id_treatment)
                .where(_PMK.id_membership_history == hist.id_history)
                .where(_PMK.is_active.is_(True))
                .where(_PMK.periode_kuota == b.periode_kuota)
            )
            if periode_val == "BULANAN":
                stmt = stmt.where(_PMK.bulan_periode == bulan_str)
            else:
                stmt = stmt.where(_PMK.bulan_periode.is_(None))
            kuota_row = self.db.execute(stmt.limit(1)).scalar_one_or_none()

            kuota_total = int(b.kuota_total or 0)
            kuota_terpakai = int(kuota_row.kuota_terpakai) if kuota_row else 0
            sisa = max(0, kuota_total - kuota_terpakai)

            result.append({
                "id_treatment": b.id_treatment,
                "nama_treatment": t.nama_treatment,
                "harga_treatment": float(t.harga or 0),
                "kuota_total": kuota_total,
                "kuota_terpakai": kuota_terpakai,
                "sisa": sisa,
                "periode_kuota": periode_val,
                "bulan_periode": (bulan_str if periode_val == "BULANAN" else None),
                "is_lazy_pending": kuota_row is None and periode_val == "BULANAN",
                "catatan": b.catatan,
            })
        return result


__all__ = ["MembershipService", "DiskonMembership"]
