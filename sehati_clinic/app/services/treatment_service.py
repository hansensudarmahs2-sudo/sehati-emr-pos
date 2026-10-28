"""
TreatmentService — perawat workflow di Ruang Tindakan.

Operasi:
- lihat_antrian_ruang_tindakan(): list pasien ANTRI_TREATMENT / ON_TREATMENT hari ini
- get_detail(id_kunjungan): SOAP dokter + daftar tindakan
- start_tindakan(id_kunjungan_tindakan, id_staf_perawat): PENDING → PROSES + transition kunjungan ke ON_TREATMENT
- end_tindakan(id_kunjungan_tindakan, id_staf_perawat): PROSES → SELESAI + auto potong BHP
  + komisi bila sudah dibayar di muka (bayar dulu T2-3) + status kunjungan dari isinya
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


def tambah_bulan(d: date, n: int) -> date:
    """`d` + `n` bulan kalender; tanggal yang tak ada di bulan tujuan dijepit ke hari
    terakhirnya (31 Agu + 6 → 28/29 Feb). Batas hak prabayar (bayar dulu T4-1)."""
    import calendar
    bulan = d.month - 1 + n
    tahun, bulan = d.year + bulan // 12, bulan % 12 + 1
    return date(tahun, bulan, min(d.day, calendar.monthrange(tahun, bulan)[1]))


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
                id_transaksi=t.id_transaksi,
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

            # Status kunjungan dari isinya (bayar dulu T1-4). Ada tindakan PROSES → fungsi
            # menghasilkan ON_TREATMENT, sama dengan paksaan lama — tapi kini lewat satu
            # definisi, bukan tebakan di sini.
            kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
            status_kunjungan_lama = kunjungan.status_antrian if kunjungan else None
            status_kunjungan_baru = status_kunjungan_lama
            if kunjungan:
                self.db.flush()
                from app.services._status_kunjungan import hitung_ulang_status
                status_kunjungan_baru = hitung_ulang_status(self.db, kunjungan.id_kunjungan)

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
            if kunjungan and status_kunjungan_baru != status_kunjungan_lama:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_pelaksana,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": status_kunjungan_lama},
                    data_baru={"status_antrian": status_kunjungan_baru},
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
                    # Tanpa ini, route web jatuh ke jalur cadangan dan memantulkan
                    # petugas balik ke daftar Antri Tindakan setiap kali menekan Mulai —
                    # padahal dia sedang mengerjakan pasien di halaman itu.
                    "id_kunjungan": tindakan.id_kunjungan,
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
        # Audit T3-8 (2026-10-13): BERKUNCI. Langkah 2 memotong BHP; dulu pagar PROSES di
        # bawah membaca tanpa kunci, jadi klik ganda yang tiba bersamaan sama-sama lolos dan
        # memotong BHP dua kali (laten: treatment_komponen masih kosong di dev).
        tindakan = self.treatment_repo.get_tindakan_for_update(id_kunjungan_tindakan)
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

            # 2b. Komisi (bayar dulu T2-3): komisi tindakan = dibayar DAN selesai, mana pun
            # yang terakhir. Sudah dibayar di muka → dicatat SEKARANG, terikat transaksi
            # pembayarnya (jadi void transaksi itu ikut menariknya), bertanggal SELESAI.
            # Belum dibayar (id_transaksi NULL) → tidak ada apa-apa; pembayaran nanti yang
            # mencatat (`catat_komisi_transaksi`). Tanpa langkah ini tindakan prabayar tidak
            # pernah berkomisi — tagihan susulan yang dulu menangkapnya tak terjadi lagi.
            # Transaksi pembayar yang sudah VOID ditolak di dalam `catat_komisi_tindakan`.
            # `tindakan` dibaca FOR UPDATE di atas → `id_transaksi`-nya terbaru.
            if tindakan.id_transaksi is not None:
                from app.services.komisi_service import KomisiService
                KomisiService(self.db).catat_komisi_tindakan(
                    kt=tindakan, id_transaksi=tindakan.id_transaksi,
                    tanggal=now.date(), request=request,
                )

            # 3. Status kunjungan dari isinya (bayar dulu T1-4). Dulu: "tak ada tindakan
            # PENDING/PROSES lagi → ANTRI_BAYAR" TANPA SYARAT — walau tindakan ini sudah
            # lunas lebih dulu (bayar dulu) dan yang tersisa hanya obat lunas di apotek.
            # Sekarang: tindakan SELESAI tanpa id_transaksi → (K) ANTRI_BAYAR; masih ada
            # tindakan lain → tetap di ruang tindakan; tak ada yang tersisa → maju.
            kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
            status_kunjungan_lama = kunjungan.status_antrian if kunjungan else None
            status_kunjungan_baru = status_kunjungan_lama
            if kunjungan:
                self.db.flush()
                from app.services._status_kunjungan import hitung_ulang_status
                status_kunjungan_baru = hitung_ulang_status(self.db, kunjungan.id_kunjungan)

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
            if kunjungan and status_kunjungan_baru != status_kunjungan_lama:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=id_staf_pelaksana,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": status_kunjungan_lama},
                    data_baru={"status_antrian": status_kunjungan_baru},
                    keterangan="Auto-transition: tindakan selesai (status dihitung dari isi kunjungan).",
                    request=request,
                )

            self.db.commit()
            self.db.refresh(tindakan)

            _lanjutan = {
                "ANTRI_BAYAR": "Semua tindakan selesai — pasien ke Kasir.",
                "ANTRI_OBAT": "Semua tindakan selesai & sudah lunas — pasien ke Apotek.",
                "COMPLETED": "Semua tindakan selesai & sudah lunas.",
            }
            message = (
                "Tindakan selesai. BHP terpotong & tercatat di kartu stok. "
                + _lanjutan.get(status_kunjungan_baru, "Masih ada tindakan lain yang tertunda.")
            )
            return {
                "status": "success",
                "message": message,
                "data": {
                    "id_kunjungan_tindakan": id_kunjungan_tindakan,
                    # Sama seperti start_tindakan: route web butuh ini supaya petugas
                    # tetap di halaman tindakan dan bisa mengerjakan tindakan berikutnya.
                    "id_kunjungan": tindakan.id_kunjungan,
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

    # =========================================================================
    # BATALKAN — PENDING & belum dibayar → BATAL (Ruling 12, bayar dulu)
    # =========================================================================
    _MIN_ALASAN_BATAL = 5

    def batalkan_tindakan(
        self,
        id_kunjungan_tindakan: int,
        alasan: str,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """Pasien menolak tindakan yang belum dikerjakan & belum dibayar.

        Spec DESAIN_BAYAR_DULU_BERCABANG.md §3.6, cabang "belum dibayar" (ditarik maju dari
        tahap 3). Kenapa sekarang: sejak bayar dulu kasir bisa menagih konsul/obat sementara
        tindakan masih PENDING. Kalau pasien lalu menolak tindakannya, satu-satunya jalan
        dulu adalah Batal KUNJUNGAN — yang ditolak karena sudah ada pembayaran — sehingga
        tindakan itu menggantung PENDING, kunjungan tak pernah COMPLETED, dan tutup kasir
        terhalang selamanya.

        - Hanya PENDING (CLAUDE.md §7: void/batal hanya untuk yang belum dikerjakan).
        - Hanya yang belum dibayar (`id_transaksi IS NULL`). Yang sudah dibayar butuh hak
          pasien / refund (tahap 4) — uangnya ada, tidak boleh dibatalkan diam-diam.
        - Pengembalian kuota & series lewat `_batal_tindakan.bereskan_satu_tindakan` — SATU
          aturan dengan Batal kunjungan (`KunjunganService._bereskan_batal`).
        """
        from app.services._baca_segar import mulai_baca_segar
        from app.services._batal_tindakan import bereskan_satu_tindakan
        from app.services._status_kunjungan import hitung_ulang_status

        alasan_bersih = (alasan or "").strip()
        if len(alasan_bersih) < self._MIN_ALASAN_BATAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Alasan pembatalan wajib diisi (minimal {self._MIN_ALASAN_BATAL} "
                        f"karakter)."),
            )
        # Pola baca-segar (app/services/_baca_segar.py): tutup potret dulu, lalu kunci. Tanpa
        # itu bayar yang baru saja menagih tindakan ini (commit selagi kita menunggu) tak
        # terlihat dan tindakan yang SUDAH DIBAYAR dibatalkan. ⚠ Jangan sisipkan SELECT
        # biasa sebelum kunci di bawah.
        #
        # Bayar dulu T2-1 (fix round 1, Ruling P3): kunci KUNJUNGAN dulu, baru tindakan —
        # urutan yang sama dengan bayar/serah/void/refund (`refund_item_tertunda`). Sejak
        # tahap 2 kasir menagih tindakan PENDING: dulu Batalkan hanya mengunci baris
        # tindakan, jadi bayar yang sedang berjalan (memegang kunci kunjungan, tagihannya
        # sudah memuat tindakan ini) tak tertahan — Batalkan commit BATAL + kuota kembali,
        # lalu bayar menautkan tindakan BATAL itu dan pasien membayarnya. id_kunjungan
        # dibaca SEBELUM baca-segar (pola `refund_item_tertunda`): kolom itu tak pernah
        # berubah, dan SELECT sesudah `mulai_baca_segar` akan membuka potret sebelum kunci.
        from sqlalchemy import select as _select
        from app.db.models import KunjunganTindakan as _KT
        _id_kj = self.db.execute(
            _select(_KT.id_kunjungan).where(_KT.id_kunjungan_tindakan == id_kunjungan_tindakan)
        ).scalar_one_or_none()
        mulai_baca_segar(self.db)
        if _id_kj is not None:
            self.kunjungan_repo.get_by_id_for_update(_id_kj)
        tindakan = self.treatment_repo.get_tindakan_for_update(id_kunjungan_tindakan)
        if tindakan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tindakan {id_kunjungan_tindakan} tidak ditemukan.",
            )
        st = getattr(tindakan.status_tindakan, "value", tindakan.status_tindakan)
        if tindakan.id_transaksi is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("Tindakan ini sudah dibayar — tidak bisa dibatalkan biasa (uangnya "
                        "ada). Pakai tombol 'Simpan sebagai hak' (dipakai di kunjungan lain) "
                        "atau minta kasir mengembalikan uangnya."),
            )
        if st != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Hanya tindakan yang belum dikerjakan dan belum dibayar yang bisa "
                        f"dibatalkan. Tindakan ini sudah dikerjakan (status '{st}') — "
                        f"tagih lewat kasir."),
            )

        try:
            hasil = bereskan_satu_tindakan(self.db, self.audit, tindakan,
                                           actor_id_staf=actor_id_staf, request=request)
            tindakan.status_tindakan = "BATAL"
            self.db.flush()
            kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
            status_lama = getattr(kunjungan.status_antrian, "value", kunjungan.status_antrian)
            status_baru = hitung_ulang_status(self.db, tindakan.id_kunjungan)
            self.audit.log(
                aksi="TINDAKAN_BATAL",
                id_staf=actor_id_staf,
                tabel_target="kunjungan_tindakan",
                id_target=id_kunjungan_tindakan,
                data_lama={"status_tindakan": "PENDING"},
                data_baru={"status_tindakan": "BATAL", "alasan": alasan_bersih,
                           "kuota_dikembalikan": hasil["kuota"],
                           "series_dibatalkan": hasil["series_cancel"],
                           "sesi_dikembalikan": hasil["sesi_kembali"],
                           "status_kunjungan": status_baru},
                keterangan=f"Tindakan dibatalkan (belum dikerjakan, belum dibayar): {alasan_bersih}",
                request=request,
            )
            if status_baru != status_lama:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=actor_id_staf,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": status_lama},
                    data_baru={"status_antrian": status_baru},
                    keterangan="Auto-transition: tindakan dibatalkan (status dihitung dari isi kunjungan).",
                    request=request,
                )
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal membatalkan tindakan: {e!s}",
            )
        return {
            "status": "success",
            "message": "Tindakan dibatalkan.",
            "data": {
                "id_kunjungan_tindakan": id_kunjungan_tindakan,
                "id_kunjungan": tindakan.id_kunjungan,
                "status_baru": "BATAL",
                "status_kunjungan_baru": status_baru,
            },
        }

    # =========================================================================
    # SIMPAN SEBAGAI HAK — tindakan SUDAH dibayar lalu ditolak (bayar dulu tahap 4, T4-1)
    # =========================================================================
    _BULAN_HAK = 6

    def simpan_sebagai_hak(
        self,
        id_kunjungan_tindakan: int,
        alasan: str,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """Pasien menolak tindakan yang belum dikerjakan tapi SUDAH dibayar di muka.

        Spec DESAIN_BAYAR_DULU_BERCABANG.md §3.6 cabang "sudah dibayar", rencana
        RENCANA_BAYAR_DULU_TAHAP4.md T4-1. Uangnya ada, jadi tindakan tidak boleh hilang
        begitu saja: ia ditukar dengan hak yang dipakai di kunjungan lain. Bentuk haknya
        mengikuti CARA tindakan itu dibayar — aturan yang sama dengan `_compute_charge`:

        - kuota member (Rp 0)  → kuota dikembalikan (P1, dr. Hansen 2026-10-28). Kuota sudah
          hak dengan batasnya sendiri; hak PRABAYAR Rp 0 hanya menggandakannya.
        - sesi series (sesi 1 pembawa harga paket, atau sesi 2..N Rp 0) → sesi itu kembali
          PENDING, bisa dipakai lagi lewat "Pakai Sesi" (P1/P2). ⚠ BUKAN
          `bereskan_satu_tindakan`: di sana sesi 1 yang lahir di kunjungan ini membatalkan
          SELURUH series — benar sebelum bayar, salah sesudahnya (paketnya sudah lunas).
        - selain itu (harga treatment) → hak PRABAYAR baru, berlaku sampai tanggal BAYAR +
          6 bulan. `id_kunjungan_pembuat` SENGAJA NULL (asal lewat `id_referensi_sumber` =
          tindakan ini): `_series` mengelompokkan series per (pasien, treatment, kunjungan
          pembuat) — dengan kunjungan pembuat terisi, hak ini terbaca "sesi 1 series
          berikutnya" dan memotong series dokter treatment yang sama.

        `id_transaksi` tindakan TIDAK dikosongkan — itu jejak transaksi yang membayarnya
        (nilai hak = snapshot `transaksi_detail_tindakan`, tanpa rumus baru). Omzet tidak
        berubah: uangnya sudah dibukukan saat dibayar.

        Hanya PENDING (CLAUDE.md §7). Peran pemanggil = Batalkan (`require_perawat_role`).
        """
        from sqlalchemy import select as _select
        from app.db.models import KunjunganTindakan as _KT
        from app.db.models import (
            MasterTreatment,
            PasienRencanaTreatment,
            StatusRencanaTreatmentEnum,
            TransaksiDetailTindakan,
            TransaksiKasir,
        )
        from app.db.models._enums import SumberRencanaEnum
        from app.services._baca_segar import mulai_baca_segar
        from app.services._batal_tindakan import kembalikan_kuota, kembalikan_sesi
        from app.services._status_kunjungan import hitung_ulang_status

        alasan_bersih = (alasan or "").strip()
        if len(alasan_bersih) < self._MIN_ALASAN_BATAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Alasan wajib diisi (minimal {self._MIN_ALASAN_BATAL} karakter).",
            )
        # Urutan kunci SAMA dengan `batalkan_tindakan` (lihat komentarnya): baca-segar →
        # kunjungan → tindakan. Void mengunci kunjungan yang sama, jadi sesudah kunci ini
        # transaksi pembayar tak bisa berubah status di bawah kita — ia dibaca biasa, TIDAK
        # dikunci (void mengunci transaksi → kunjungan; urutan sebaliknya = deadlock).
        _id_kj = self.db.execute(
            _select(_KT.id_kunjungan).where(_KT.id_kunjungan_tindakan == id_kunjungan_tindakan)
        ).scalar_one_or_none()
        mulai_baca_segar(self.db)
        if _id_kj is not None:
            self.kunjungan_repo.get_by_id_for_update(_id_kj)
        tindakan = self.treatment_repo.get_tindakan_for_update(id_kunjungan_tindakan)
        if tindakan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tindakan {id_kunjungan_tindakan} tidak ditemukan.",
            )
        st = getattr(tindakan.status_tindakan, "value", tindakan.status_tindakan)
        if st != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Hanya tindakan yang belum dikerjakan yang bisa disimpan sebagai hak. "
                        f"Status tindakan ini '{st}'."),
            )
        if tindakan.id_transaksi is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tindakan ini belum dibayar — pakai tombol 'Batalkan'.",
            )
        trx = self.db.get(TransaksiKasir, tindakan.id_transaksi)
        if trx is None or trx.status_transaksi != "BAYAR":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"Transaksi #{tindakan.id_transaksi} yang menagih tindakan ini tidak "
                        f"berstatus BAYAR. Muat ulang halaman."),
            )
        rencana = None
        if tindakan.id_kuota_member is None and tindakan.id_rencana is not None:
            rencana = self.db.get(PasienRencanaTreatment, tindakan.id_rencana)
            if rencana is None or rencana.status != StatusRencanaTreatmentEnum.SCHEDULED:
                # Hanya sesi SCHEDULED yang bisa kembali PENDING. Menulis BATAL tanpa itu =
                # hak pasien hilang tanpa pengganti — tolak, biar dibereskan Admin.
                st_r = getattr(getattr(rencana, "status", None), "value", None)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(f"Sesi series #{tindakan.id_rencana} berstatus '{st_r}', tidak "
                            f"bisa dikembalikan sebagai hak. Hubungi Admin."),
                )

        try:
            data_audit: dict = {"status_tindakan": "BATAL", "alasan": alasan_bersih,
                                "id_transaksi": trx.id_transaksi}
            id_rencana_hak = None
            if tindakan.id_kuota_member is not None:
                bentuk = "KUOTA"
                data_audit["kuota_dikembalikan"] = kembalikan_kuota(
                    self.db, [tindakan], actor_id_staf=actor_id_staf,
                    id_kunjungan=tindakan.id_kunjungan, request=request)
            elif rencana is not None:
                bentuk = "SESI"
                kembalikan_sesi(self.db, self.audit, [rencana],
                                trigger=f"hak_tindakan_{id_kunjungan_tindakan}",
                                actor_id_staf=actor_id_staf, request=request)
                data_audit["id_rencana_dikembalikan"] = rencana.id_rencana
            else:
                bentuk = "HAK"
                tr = self.db.get(MasterTreatment, tindakan.id_treatment)
                tgl_bayar = (trx.waktu_bayar or datetime.now()).date()
                hak = PasienRencanaTreatment(
                    id_pasien=self.kunjungan_repo.get_by_id(tindakan.id_kunjungan).id_pasien,
                    id_treatment=tindakan.id_treatment,
                    urutan_sesi=1,
                    nama_tindakan=((tr.nama_treatment if tr else None)
                                   or f"Tindakan #{tindakan.id_treatment}")[:100],
                    sumber_rencana=SumberRencanaEnum.PRABAYAR,
                    id_referensi_sumber=tindakan.id_kunjungan_tindakan,
                    id_kunjungan_pembuat=None,
                    status=StatusRencanaTreatmentEnum.PENDING,
                    tgl_target_mulai=tgl_bayar,
                    tgl_target_akhir=tambah_bulan(tgl_bayar, self._BULAN_HAK),
                    catatan_dokter=(f"Hak prabayar dari tindakan #{tindakan.id_kunjungan_tindakan} "
                                    f"(transaksi #{trx.id_transaksi})."),
                )
                self.db.add(hak)
                self.db.flush()
                id_rencana_hak = hak.id_rencana
                nilai = self.db.execute(
                    _select(TransaksiDetailTindakan.subtotal)
                    .where(TransaksiDetailTindakan.id_transaksi == trx.id_transaksi)
                    .where(TransaksiDetailTindakan.id_kunjungan_tindakan == tindakan.id_kunjungan_tindakan)
                ).scalars().first()
                data_audit.update({"id_rencana": id_rencana_hak,
                                   "nilai": str(nilai) if nilai is not None else None,
                                   "berlaku_sampai": hak.tgl_target_akhir.isoformat()})
            data_audit["bentuk"] = bentuk

            tindakan.status_tindakan = "BATAL"
            self.db.flush()
            kunjungan = self.kunjungan_repo.get_by_id(tindakan.id_kunjungan)
            status_lama = getattr(kunjungan.status_antrian, "value", kunjungan.status_antrian)
            status_baru = hitung_ulang_status(self.db, tindakan.id_kunjungan)
            data_audit["status_kunjungan"] = status_baru
            self.audit.log(
                aksi="TINDAKAN_JADI_HAK",
                id_staf=actor_id_staf,
                tabel_target="kunjungan_tindakan",
                id_target=id_kunjungan_tindakan,
                data_lama={"status_tindakan": "PENDING"},
                data_baru=data_audit,
                keterangan=f"Tindakan dibayar tapi tidak dikerjakan → hak ({bentuk}): {alasan_bersih}",
                request=request,
            )
            if status_baru != status_lama:
                self.audit.log(
                    aksi="STATUS_UPDATE",
                    id_staf=actor_id_staf,
                    tabel_target="kunjungan",
                    id_target=tindakan.id_kunjungan,
                    data_lama={"status_antrian": status_lama},
                    data_baru={"status_antrian": status_baru},
                    keterangan="Auto-transition: tindakan disimpan sebagai hak (status dihitung dari isi kunjungan).",
                    request=request,
                )
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal menyimpan sebagai hak: {e!s}",
            )
        pesan = {"KUOTA": "Kuota membership dikembalikan.",
                 "SESI": "Sesi series dikembalikan — bisa dipakai lagi lewat 'Pakai Sesi'.",
                 "HAK": "Hak tindakan disimpan — bisa dipakai di kunjungan lain."}[bentuk]
        return {
            "status": "success",
            "message": pesan,
            "data": {
                "id_kunjungan_tindakan": id_kunjungan_tindakan,
                "id_kunjungan": tindakan.id_kunjungan,
                "bentuk": bentuk,
                "id_rencana": id_rencana_hak,
                "status_kunjungan_baru": status_baru,
            },
        }
