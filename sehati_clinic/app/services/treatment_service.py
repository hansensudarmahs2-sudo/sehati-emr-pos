"""
TreatmentService — perawat workflow di Ruang Tindakan.

Operasi:
- lihat_antrian_ruang_tindakan(): list pasien ANTRI_TREATMENT / ON_TREATMENT hari ini
- get_detail(id_kunjungan): SOAP dokter + daftar tindakan
- start_tindakan(id_kunjungan_tindakan, id_staf_perawat): PENDING → PROSES + transition kunjungan ke ON_TREATMENT
- end_tindakan(id_kunjungan_tindakan, id_staf_perawat): PROSES → SELESAI + auto potong BHP + SMART CHECK → ANTRI_BAYAR
"""

from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganTindakan,
    PemeriksaanKlinis,
)
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.treatment_repo import TreatmentRepository
from app.schemas.treatment import (
    AntrianRuangTindakanItem,
    AntrianRuangTindakanResponse,
    CatatanDokterDetail,
    DetailRuangTindakanResponse,
    TindakanDetailItem,
)
from app.services.audit_service import AuditService
from app.services.inventory_service import InventoryService


class TreatmentService:
    def __init__(self, db: Session):
        self.db = db
        self.treatment_repo = TreatmentRepository(db)
        self.kunjungan_repo = KunjunganRepository(db)
        self.audit = AuditService(db)
        self.inventory = InventoryService(db)

    # =========================================================================
    # ANTRIAN — perawat dashboard
    # =========================================================================
    def lihat_antrian(self, today: Optional[date] = None, user=None) -> AntrianRuangTindakanResponse:
        if today is None:
            today = date.today()

        rows = self.treatment_repo.list_antrian_ruang_tindakan(today=today)

        # K-L0 (DEC-087): kalau yang login DOKTER (bukan admin/owner/superadmin), tampilkan
        # HANYA pasien yang di-assign ke dia + pasien "bebas" (tanpa dokter). Perawat & manajemen
        # tetap melihat semua. Dokter pengganti harus di-assign FO dulu sebelum melihat pasiennya.
        if user is not None:
            _role = (user.role.value if hasattr(user.role, "value") else str(user.role or "")).upper()
            if _role == "DOKTER":
                uid = user.id_staf
                rows = [
                    r for r in rows
                    if r[0].id_staf_dokter_assigned in (uid, None)
                ]
        items = [
            AntrianRuangTindakanItem(
                id_kunjungan=k.id_kunjungan,
                nomor_antrean=k.nomor_antrean,
                status_antrian=k.status_antrian,
                tgl_kunjungan=k.tgl_kunjungan,
                keluhan_utama=k.keluhan_utama,
                id_pasien=p.id_pasien,
                no_rm=p.no_rm,
                nama_pasien=p.nama,
                tgl_lahir=p.tgl_lahir,
                tindakan_pending=n_pending,
                tindakan_proses=n_proses,
                total_tindakan=n_pending + n_proses,
            )
            for k, p, n_pending, n_proses in rows
        ]
        return AntrianRuangTindakanResponse(tanggal=today, total=len(items), data=items)

    # =========================================================================
    # DETAIL — iPad ruang tindakan (SOAP + daftar tindakan)
    # =========================================================================
    def get_detail(self, id_kunjungan: int) -> DetailRuangTindakanResponse:
        kunjungan_pasien = self.treatment_repo.get_kunjungan_with_pasien(id_kunjungan)
        if kunjungan_pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {id_kunjungan} tidak ditemukan.",
            )
        kunjungan, pasien = kunjungan_pasien

        soap = self.treatment_repo.get_pemeriksaan_klinis(id_kunjungan)
        instruksi = None
        if soap is not None:
            instruksi = CatatanDokterDetail(
                anamnesa=soap.anamnesa,
                pemeriksaan_fisik=soap.pemeriksaan_fisik,
                diagnosa=soap.diagnosa,
                saran_treatment=soap.saran_treatment,
                saran_produk=soap.saran_produk,
            )

        tindakan_rows = self.treatment_repo.list_tindakan_for_kunjungan(id_kunjungan)
        daftar = [
            TindakanDetailItem(
                id_kunjungan_tindakan=t.id_kunjungan_tindakan,
                id_treatment=t.id_treatment,
                nama_treatment=tr.nama_treatment,
                role_pelaksana=tr.role_pelaksana,  # TODO-NEW-5 #33
                status_tindakan=(
                    t.status_tindakan.value
                    if hasattr(t.status_tindakan, "value")
                    else str(t.status_tindakan) if t.status_tindakan else None
                ),
                waktu_mulai=t.waktu_mulai,
                waktu_selesai=t.waktu_selesai,
                id_staf_pelaksana=t.id_staf_pelaksana,
                nama_staf_pelaksana=(staf.nama_staf if staf else None),
            )
            for t, tr, staf in tindakan_rows
        ]

        return DetailRuangTindakanResponse(
            id_kunjungan=kunjungan.id_kunjungan,
            id_pasien=pasien.id_pasien,
            no_rm=pasien.no_rm,
            nama_pasien=pasien.nama,
            status_kunjungan=kunjungan.status_antrian,
            instruksi_dokter=instruksi,
            daftar_tindakan=daftar,
        )

    # =========================================================================
    # START — PENDING → PROSES
    # =========================================================================
    def start_tindakan(
        self,
        id_kunjungan_tindakan: int,
        id_staf_pelaksana: int,
        request: Optional[Request] = None,
        user_role=None,  # TODO-NEW-5 #33: untuk role guardrail
    ) -> dict:
        tindakan = self.treatment_repo.get_tindakan_by_id(id_kunjungan_tindakan)
        if tindakan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tindakan {id_kunjungan_tindakan} tidak ditemukan.",
            )

        status_sekarang = (
            tindakan.status_tindakan.value
            if hasattr(tindakan.status_tindakan, "value")
            else str(tindakan.status_tindakan)
        )
        if status_sekarang != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tindakan tidak bisa dimulai — status saat ini '{status_sekarang}', "
                    f"hanya 'PENDING' yang bisa di-start."
                ),
            )

        # TODO-NEW-5 #33 (11 Juni 2026): role_pelaksana guardrail.
        # Treatment role DOKTER → hanya DOKTER yang boleh start (Admin/Owner bypass).
        # Treatment role PERAWAT → semua perawat-eligible role boleh.
        if user_role is not None:
            from app.db.models import MasterTreatment
            treatment = self.db.get(MasterTreatment, tindakan.id_treatment)
            if treatment is not None:
                treatment_role = (treatment.role_pelaksana or "").strip().upper()
                user_role_str = user_role.value if hasattr(user_role, "value") else str(user_role)
                user_role_upper = user_role_str.upper()
                bypass_roles = {"ADMIN", "OWNER", "SUPERADMIN"}
                if user_role_upper not in bypass_roles:
                    if treatment_role == "DOKTER" and user_role_upper != "DOKTER":
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=(
                                f"Tindakan '{treatment.nama_treatment}' hanya bisa dilakukan oleh "
                                f"DOKTER. Role Anda: {user_role_str}. Hubungi dokter untuk eksekusi."
                            ),
                        )

        try:
            # BUG-1517 fix: pakai datetime.now() (local time) konsisten dengan
            # waktu_bayar di transaksi_kasir dan waktu_input di kunjungan_resep.
            # datetime.utcnow() bikin selisih 7 jam (WIB=UTC+7) sehingga filter
            # cutoff di KasirService.get_tagihan gagal detect tindakan baru.
            now = datetime.now()
            self.treatment_repo.update_status_tindakan(
                tindakan,
                status_baru="PROSES",
                id_staf_pelaksana=id_staf_pelaksana,
                waktu_mulai=now,
            )

            # Transition kunjungan ke ON_TREATMENT (kalau belum)
            kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
            status_kunjungan_lama = kunjungan.status_antrian if kunjungan else None
            if kunjungan and kunjungan.status_antrian != "ON_TREATMENT":
                self.kunjungan_repo.update_status(kunjungan, "ON_TREATMENT")

            # K-L0 (komisi, DEC-087): rekam pelaksana untuk atribusi komisi.
            # - Operator dokter → dia = pelaksana dokter (komisi_dokter).
            # - Operator perawat → pelaksana perawat (komisi_perawat) + komisi_dokter ke dokter pengawas.
            _role_up = (user_role.value if hasattr(user_role, "value") else str(user_role or "")).upper()
            if _role_up == "DOKTER":
                # Dokter yang mengeksekusi = pelaksana dokter (benar utk assigned, pengganti, & bebas).
                tindakan.id_dokter_pelaksana = id_staf_pelaksana
            elif kunjungan is not None:
                # Operator bukan dokter (mis. perawat) → komisi_dokter ke dokter pengawas (yang di-assign).
                tindakan.id_dokter_pelaksana = kunjungan.id_staf_dokter_assigned
            if _role_up == "PERAWAT":
                tindakan.id_perawat_pelaksana = id_staf_pelaksana

            # AUDIT
            self.audit.log(
                aksi="TINDAKAN_START",
                id_staf=id_staf_pelaksana,
                tabel_target="kunjungan_tindakan",
                id_target=id_kunjungan_tindakan,
                data_lama={"status_tindakan": "PENDING"},
                data_baru={
                    "status_tindakan": "PROSES",
                    "id_staf_pelaksana": id_staf_pelaksana,
                    "id_dokter_pelaksana": tindakan.id_dokter_pelaksana,
                    "id_perawat_pelaksana": tindakan.id_perawat_pelaksana,
                    "waktu_mulai": now.isoformat(),
                },
                request=request,
            )
            if kunjungan and status_kunjungan_lama != "ON_TREATMENT":
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_pelaksana,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": status_kunjungan_lama},
                    data_baru={"status_antrian": "ON_TREATMENT"},
                    keterangan="Auto-transition saat tindakan pertama di-start.",
                    request=request,
                )

            self.db.commit()
            self.db.refresh(tindakan)
            return {
                "status": "success",
                "message": "Tindakan dimulai. Stopwatch aktif.",
                "data": {
                    "id_kunjungan_tindakan": id_kunjungan_tindakan,
                    "status_baru": "PROSES",
                    "waktu_mulai": now.isoformat(),
                    "id_staf_pelaksana": id_staf_pelaksana,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal start tindakan: {str(e)}",
            )

    # =========================================================================
    # END — PROSES → SELESAI + auto potong BHP + SMART CHECK
    # =========================================================================
    def end_tindakan(
        self,
        id_kunjungan_tindakan: int,
        id_staf_pelaksana: int,
        request: Optional[Request] = None,
    ) -> dict:
        tindakan = self.treatment_repo.get_tindakan_by_id(id_kunjungan_tindakan)
        if tindakan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tindakan {id_kunjungan_tindakan} tidak ditemukan.",
            )

        status_sekarang = (
            tindakan.status_tindakan.value
            if hasattr(tindakan.status_tindakan, "value")
            else str(tindakan.status_tindakan)
        )
        if status_sekarang != "PROSES":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tindakan tidak bisa diakhiri — status saat ini '{status_sekarang}', "
                    f"hanya 'PROSES' yang bisa di-end."
                ),
            )

        try:
            # 1. Status tindakan → SELESAI
            # BUG-1517 fix: pakai datetime.now() (local time) konsisten dengan
            # waktu_bayar di transaksi_kasir dan waktu_input di kunjungan_resep.
            # datetime.utcnow() bikin selisih 7 jam (WIB=UTC+7) sehingga filter
            # cutoff di KasirService.get_tagihan gagal detect tindakan baru.
            now = datetime.now()
            self.treatment_repo.update_status_tindakan(
                tindakan,
                status_baru="SELESAI",
                waktu_selesai=now,
            )

            # 2. Auto potong BHP — id_staf yang dicatat di history adalah
            #    pelaksana, fallback ke current actor kalau pelaksana null.
            id_staf_history = tindakan.id_staf_pelaksana or id_staf_pelaksana
            hasil_potong = self.inventory.deduct_for_treatment(
                id_treatment=tindakan.id_treatment,
                id_kunjungan_tindakan=id_kunjungan_tindakan,
                id_kunjungan=tindakan.id_kunjungan,
                id_staf=id_staf_history,
            )

            # 3. SMART CHECK — masih ada tindakan PENDING/PROSES?
            sisa = self.treatment_repo.count_tindakan_aktif(tindakan.id_kunjungan)
            status_kunjungan_baru = None
            if sisa == 0:
                kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
                if kunjungan:
                    self.kunjungan_repo.update_status(kunjungan, "ANTRI_BAYAR")
                    status_kunjungan_baru = "ANTRI_BAYAR"

            # 4. AUDIT
            self.audit.log(
                aksi="TINDAKAN_END",
                id_staf=id_staf_pelaksana,
                tabel_target="kunjungan_tindakan",
                id_target=id_kunjungan_tindakan,
                data_lama={"status_tindakan": "PROSES"},
                data_baru={
                    "status_tindakan": "SELESAI",
                    "waktu_selesai": now.isoformat(),
                    "jumlah_bahan_potong": len(hasil_potong),
                },
                request=request,
            )
            if status_kunjungan_baru:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_pelaksana,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": "ON_TREATMENT"},
                    data_baru={"status_antrian": "ANTRI_BAYAR"},
                    keterangan="Auto-transition: semua tindakan selesai.",
                    request=request,
                )

            self.db.commit()
            self.db.refresh(tindakan)

            message = (
                "Tindakan selesai. BHP terpotong & tercatat di kartu stok. "
                + (
                    "Semua tindakan selesai — pasien ke Kasir."
                    if status_kunjungan_baru == "ANTRI_BAYAR"
                    else "Masih ada tindakan lain yang tertunda."
                )
            )
            return {
                "status": "success",
                "message": message,
                "data": {
                    "id_kunjungan_tindakan": id_kunjungan_tindakan,
                    "status_baru": "SELESAI",
                    "status_kunjungan_baru": status_kunjungan_baru,
                    "jumlah_bhp_terpotong": len(hasil_potong),
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal end tindakan: {str(e)}",
            )
