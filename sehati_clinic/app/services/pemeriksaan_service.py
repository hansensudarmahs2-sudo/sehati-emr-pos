"""
PemeriksaanService — business logic untuk SOAP dokter + tindakan + resep.

Pattern dari kode dokter Bapak (`/dokter/input_medis`):
- 1 endpoint compound yang melakukan 4 hal atomik dalam 1 transaksi:
  1. INSERT pemeriksaan_klinis (SOAP: anamnesa, PF, diagnosa, saran)
  2. INSERT tindakan baru:
     - Single → kunjungan_tindakan (status PENDING, untuk perawat ambil hari ini)
     - Series → N rows ke pasien_rencana_treatment (sesi 1..N)
  3. INSERT kunjungan_resep (kalau dokter resepkan produk)
  4. UPDATE kunjungan.status_antrian (transition KONSULTASI → ANTRI_TREATMENT atau ANTRI_BAYAR)

Audit log:
- log_create per tabel: pemeriksaan_klinis, kunjungan_tindakan (per item), pasien_rencana_treatment (per series), kunjungan_resep (per item)
- Tidak log isi anamnesa/diagnosa raw (PII medis) — hanya catat counter & id.
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    KunjunganTindakan,
    MasterStaf,
    PasienRencanaTreatment,
    PemeriksaanKlinis,
    StatusRencanaTreatmentEnum,
)
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.pasien_repo import PasienRepository
from app.repositories.pemeriksaan_repo import PemeriksaanRepository
from app.schemas.pemeriksaan import (
    AlergiRingkasItem,
    AntrianDokterItem,
    AntrianDokterResponse,
    AntropometriHeaderData,
    CounterStatusAntrian,
    DetailHoverIdentitas,
    GridAlergi,
    GridAntropometri,
    GridIdentitas,
    HeaderPasienResponse,
    InputMedisRequest,
    ProdukDibeliRingkas,
    SoapRingkasItem,
    SummaryDokterResponse,
    TreatmentSelesaiRingkas,
)
from app.services.antropometri_service import AntropometriService
from app.services.audit_service import AuditService


def _ringkas_teks(teks: Optional[str], batas: int = 50) -> str:
    """Truncate teks panjang untuk display di cardbox (dari kode lama)."""
    if not teks:
        return "-"
    return teks if len(teks) <= batas else teks[:batas] + "..."


class PemeriksaanService:
    def __init__(self, db: Session):
        self.db = db
        self.pemeriksaan_repo = PemeriksaanRepository(db)
        self.kunjungan_repo = KunjunganRepository(db)
        self.pasien_repo = PasienRepository(db)
        self.antropometri = AntropometriService(db)
        self.audit = AuditService(db)

    # =========================================================================
    # INPUT MEDIS — endpoint utama dokter (compound atomic)
    # =========================================================================
    def input_medis_lengkap(
        self,
        payload: InputMedisRequest,
        id_staf_dokter: int,
        request: Optional[Request] = None,
    ) -> dict:
        """
        Submit SOAP + tindakan + resep + transition status.

        Validasi:
        - Kunjungan exists & belum COMPLETED/BATAL
        - id_pasien match dengan kunjungan.id_pasien
        - Minimal 1 dari (anamnesa, PF, diagnosa) terisi
        - Semua id_treatment & id_produk exists di master
        """
        # ----- 1. VALIDASI BASIC -----
        kunjungan = self.kunjungan_repo.get_by_id(payload.id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan {payload.id_kunjungan} tidak ditemukan.",
            )
        if kunjungan.id_pasien != payload.id_pasien:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"id_pasien {payload.id_pasien} tidak match dengan kunjungan "
                    f"(yang seharusnya {kunjungan.id_pasien})."
                ),
            )
        if kunjungan.status_antrian in ("COMPLETED", "BATAL"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Kunjungan sudah {kunjungan.status_antrian} — "
                    "tidak bisa input medis lagi."
                ),
            )

        # FO-ASSIGN-DOKTER (Task #329, DEC-058): hard block kalau pasien sudah
        # di-assign FO ke dokter lain. Owner exempt (bisa override).
        if (
            kunjungan.id_staf_dokter_assigned is not None
            and kunjungan.id_staf_dokter_assigned != id_staf_dokter
        ):
            current_user = self.db.get(MasterStaf, id_staf_dokter)
            is_owner = (
                current_user is not None
                and hasattr(current_user.role, "value")
                and current_user.role.value == "Owner"
            )
            if not is_owner:
                assigned_dokter = self.db.get(MasterStaf, kunjungan.id_staf_dokter_assigned)
                nama_assigned = (
                    assigned_dokter.nama_staf
                    if assigned_dokter is not None
                    else f"#{kunjungan.id_staf_dokter_assigned}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Pasien ini sudah di-assign ke {nama_assigned} oleh FO. "
                        f"Hubungi FO untuk reassignment kalau Bapak ingin handle."
                    ),
                )

        # SOAP-GUARD Day Rollover Lock (Decision A, DEC-053):
        # Rekam medis hari sebelumnya terkunci permanen. Cek tanggal SOAP existing.
        # Berlaku untuk siapa saja termasuk dokter pemeriksa asli.
        # WIB local time karena MySQL TIMESTAMP konsisten dengan datetime.now() (DEC-052).
        existing_soap = self.pemeriksaan_repo.get_latest_soap_by_kunjungan(payload.id_kunjungan)
        soap_aksi_flag = "INPUT_SOAP_NEW"  # default untuk audit
        if existing_soap is not None and existing_soap.created_at is not None:
            from datetime import date as _date
            today_wib = _date.today()
            soap_date = existing_soap.created_at.date()
            if soap_date < today_wib:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Rekam medis kunjungan ini tercatat tanggal "
                        f"{soap_date.strftime('%d %B %Y')} dan sudah TERKUNCI. "
                        "Tidak bisa tambah / ubah catatan ke kunjungan hari sebelumnya. "
                        "Daftarkan kunjungan baru untuk catatan hari ini."
                    ),
                )
            # SOAP-GUARD Owner-Check (Decision A Level Medium, DEC-053):
            # HARD BLOCK kalau dokter berbeda coba edit/append SOAP same day.
            # Hanya dokter pemeriksa asli yang boleh input SOAP ke kunjungan ini.
            # Untuk konsultasi dokter lain di hari yang sama, FO harus daftarkan
            # kunjungan baru (separate id_kunjungan) untuk pasien tersebut.
            if existing_soap.id_staf_dokter == id_staf_dokter:
                soap_aksi_flag = "UBAH_SOAP_OWN"  # dokter asli edit own SOAP same day
            else:
                # Lookup nama dokter asli untuk error message yang jelas
                original_dokter = self.db.get(MasterStaf, existing_soap.id_staf_dokter)
                nama_pemeriksa = (
                    original_dokter.nama_staf
                    if original_dokter is not None
                    else f"#{existing_soap.id_staf_dokter}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Kunjungan ini sudah dikonsultasikan oleh {nama_pemeriksa}. "
                        "Hanya dokter pemeriksa asli yang boleh menambah / mengubah "
                        "catatan untuk kunjungan ini. "
                        "Kalau pasien butuh konsultasi dokter lain hari ini, "
                        "minta FO untuk daftarkan kunjungan baru."
                    ),
                )

        # FLOW-D Part C (DEC-051): Cap max 1 reopen per kunjungan.
        # Setelah 2 transaksi (original + 1 tagihan tambahan), dokter TIDAK
        # boleh tambah tindakan baru lagi. Daftarkan kunjungan baru via FO.
        # Pengecualian: kalau tidak ada tindakan baru di payload, anggap edit
        # SOAP saja → allow (tidak picu transaksi ke-3).
        REVERTABLE_STATES = ("ANTRI_OBAT", "ANTRI_BAYAR", "ANTRI_TREATMENT", "ON_TREATMENT")
        if (
            kunjungan.status_antrian in REVERTABLE_STATES
            and len(payload.tindakan_baru) > 0
        ):
            from app.db.models import TransaksiKasir as _TK
            from sqlalchemy import select as _sel, func as _func
            count_existing_trx = self.db.execute(
                _sel(_func.count(_TK.id_transaksi))
                .where(_TK.id_kunjungan == payload.id_kunjungan)
            ).scalar() or 0
            if count_existing_trx >= 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Kunjungan ini sudah {count_existing_trx}x dibayar. "
                        "Untuk tindakan tambahan, daftarkan kunjungan baru "
                        "untuk pasien hari ini via FO. Maksimal 1x reopen "
                        "per kunjungan untuk menjaga audit trail."
                    ),
                )

        if not any([payload.anamnesa.strip(), payload.pemeriksaan_fisik.strip(), payload.diagnosa.strip()]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Minimal salah satu dari anamnesa, pemeriksaan_fisik, atau diagnosa harus diisi.",
            )

        # Validasi master_treatment & master_produk exists
        for t in payload.tindakan_baru:
            if not self.pemeriksaan_repo.get_treatment_exists(t.id_treatment):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"master_treatment dengan id {t.id_treatment} tidak ditemukan.",
                )
        for p in payload.resep_produk:
            if not self.pemeriksaan_repo.get_produk_exists(p.id_produk):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"master_produk dengan id {p.id_produk} tidak ditemukan.",
                )

        try:
            # ----- 2. INSERT SOAP -----
            soap = PemeriksaanKlinis(
                id_kunjungan=payload.id_kunjungan,
                id_pasien=payload.id_pasien,
                id_staf_dokter=id_staf_dokter,
                anamnesa=payload.anamnesa or None,
                pemeriksaan_fisik=payload.pemeriksaan_fisik or None,
                diagnosa=payload.diagnosa or None,
                saran_treatment=payload.saran_treatment or None,
                saran_produk=payload.saran_produk or None,
            )
            self.pemeriksaan_repo.create_soap(soap)
            id_pemeriksaan_baru = soap.id_pemeriksaan

            # ----- 3. INSERT TINDAKAN (single vs series) -----
            jumlah_single = 0
            jumlah_series = 0
            ada_single_hari_ini = False

            for t in payload.tindakan_baru:
                if t.is_series:
                    # SERIES (DEC-049 v2): Sesi 1 eksekusi HARI INI + sesi 2..N rencana.
                    # Untuk Kasir bisa detect "ini sesi 1 series" vs "single tindakan",
                    # SESI 1 juga buat rencana dengan urutan_sesi=1, lalu link
                    # KunjunganTindakan.id_rencana = rencana_sesi1.id_rencana.
                    # Kasir kemudian count siblings (rencana same treatment+kunjungan_pembuat)
                    # untuk tentukan total_sesi → charge paket = N × harga_paket.
                    nama_treatment_snapshot = (
                        self.pemeriksaan_repo.get_nama_treatment(t.id_treatment)
                        or "Treatment Unknown"
                    )
                    # Sesi 1 rencana (SCHEDULED — sudah di-booked ke kunjungan hari ini)
                    rencana_sesi1 = PasienRencanaTreatment(
                        id_pasien=payload.id_pasien,
                        id_treatment=t.id_treatment,
                        urutan_sesi=1,
                        nama_tindakan=nama_treatment_snapshot,
                        id_kunjungan_pembuat=payload.id_kunjungan,
                        catatan_dokter=t.catatan_dokter or None,
                        status=StatusRencanaTreatmentEnum.SCHEDULED,
                    )
                    self.pemeriksaan_repo.add_rencana_series(rencana_sesi1)
                    self.db.flush()  # supaya id_rencana ter-generate

                    # Sesi 1 kunjungan_tindakan link ke rencana
                    tindakan_sesi1 = KunjunganTindakan(
                        id_kunjungan=payload.id_kunjungan,
                        id_treatment=t.id_treatment,
                        id_rencana=rencana_sesi1.id_rencana,
                    )
                    self.pemeriksaan_repo.add_tindakan_hari_ini(tindakan_sesi1)
                    jumlah_single += 1
                    ada_single_hari_ini = True

                    # Sesi 2..N rencana (PENDING — belum di-booked, menunggu FO)
                    for sesi in range(2, t.jumlah_sesi + 1):
                        rencana = PasienRencanaTreatment(
                            id_pasien=payload.id_pasien,
                            id_treatment=t.id_treatment,
                            urutan_sesi=sesi,
                            nama_tindakan=nama_treatment_snapshot,
                            id_kunjungan_pembuat=payload.id_kunjungan,
                            catatan_dokter=t.catatan_dokter or None,
                            status=StatusRencanaTreatmentEnum.PENDING,
                        )
                        self.pemeriksaan_repo.add_rencana_series(rencana)
                    # Total sesi dijadwalkan = jumlah_sesi - 1 (sesi 1 sudah di-booked)
                    jumlah_series += max(0, t.jumlah_sesi - 1)
                else:
                    # SINGLE: 1 row ke kunjungan_tindakan untuk perawat eksekusi
                    # P2-#3 - Auto-use kuota membership kalau tersedia
                    _id_kuota_used = None
                    try:
                        from app.services.membership_service import MembershipService as _MShipSvc
                        _mship = _MShipSvc(self.db)
                        _kuota_info = _mship.get_or_create_kuota_for_treatment(
                            id_pasien=kunjungan.id_pasien,
                            id_treatment=t.id_treatment,
                        )
                        if _kuota_info is not None and _kuota_info.get("sisa", 0) > 0:
                            # Increment kuota_terpakai atomically; only set id_kuota_member kalau sukses
                            # LOG-1: pass actor + kunjungan context untuk audit KUOTA_PAKAI
                            if _mship.increment_kuota_terpakai(
                                _kuota_info["id_kuota"],
                                actor_id_staf=id_staf_dokter,
                                id_kunjungan=payload.id_kunjungan,
                                request=request,
                            ):
                                _id_kuota_used = _kuota_info["id_kuota"]
                    except Exception:
                        # Graceful fallback — kalau kuota check gagal, tetap insert tindakan normal
                        _id_kuota_used = None
                    tindakan = KunjunganTindakan(
                        id_kunjungan=payload.id_kunjungan,
                        id_treatment=t.id_treatment,
                        id_kuota_member=_id_kuota_used,
                    )
                    self.pemeriksaan_repo.add_tindakan_hari_ini(tindakan)
                    jumlah_single += 1
                    ada_single_hari_ini = True

            # ----- 4. INSERT RESEP PRODUK -----
            jumlah_resep = 0
            for p in payload.resep_produk:
                resep = KunjunganResep(
                    id_kunjungan=payload.id_kunjungan,
                    id_produk=p.id_produk,
                    qty=p.qty,
                    aturan_pakai=p.aturan_pakai or None,
                    id_staf_input=id_staf_dokter,
                )
                self.pemeriksaan_repo.add_resep(resep)
                jumlah_resep += 1

            # ----- 5. UPDATE STATUS KUNJUNGAN -----
            # Auto-transition logic — anti-regression untuk Ubah Konsul:
            # - Status ANTRI_KONSULTASI/KONSULTASI → maju ke ANTRI_TREATMENT/ANTRI_BAYAR
            # - Status sudah lebih maju (ANTRI_TREATMENT/ON_TREATMENT/ANTRI_BAYAR/
            #   ANTRI_OBAT) → JANGAN regress. Dokter sedang Ubah SOAP setelah workflow
            #   sudah berjalan, jangan kacaukan perawat/kasir/apoteker.
            # - Audit log tetap capture (siapa+kapan+is_edit) untuk traceability.
            status_lama = kunjungan.status_antrian
            INITIAL_STATES = ("ANTRI_KONSULTASI", "KONSULTASI")
            # FLOW-D Opsi C (DEC-050): dokter tambah tindakan baru ke kunjungan
            # yang sudah ANTRI_OBAT/ANTRI_BAYAR → auto-revert ke ANTRI_TREATMENT
            # supaya perawat lihat di antrian. Kasir akan bikin transaksi baru
            # untuk items belum berbayar (snapshot waktu_bayar lama).
            REVERTABLE_STATES = ("ANTRI_OBAT", "ANTRI_BAYAR")
            if status_lama in INITIAL_STATES:
                status_baru = "ANTRI_TREATMENT" if ada_single_hari_ini else "ANTRI_BAYAR"
                self.kunjungan_repo.update_status(kunjungan, status_baru)
                is_edit_after_workflow = False
            elif status_lama in REVERTABLE_STATES and jumlah_single > 0:
                # Dokter tambah tindakan baru padahal kunjungan sudah maju → revert
                status_baru = "ANTRI_TREATMENT"
                self.kunjungan_repo.update_status(kunjungan, status_baru)
                is_edit_after_workflow = True
            else:
                # Edit mode — status tetap, no regression
                status_baru = status_lama
                is_edit_after_workflow = True

            # ----- 6. AUDIT — sebelum commit -----
            # SOAP create (catat counter & ids, BUKAN isi anamnesa/diagnosa raw — PII medis)
            self.audit.log_create(
                id_staf=id_staf_dokter,
                tabel="pemeriksaan_klinis",
                id_target=id_pemeriksaan_baru,
                data_baru={
                    "id_kunjungan": payload.id_kunjungan,
                    "id_pasien": payload.id_pasien,
                    "ada_anamnesa": bool(payload.anamnesa.strip()),
                    "ada_pf": bool(payload.pemeriksaan_fisik.strip()),
                    "ada_diagnosa": bool(payload.diagnosa.strip()),
                    "ada_saran_treatment": bool(payload.saran_treatment.strip()),
                    "ada_saran_produk": bool(payload.saran_produk.strip()),
                    "jumlah_tindakan_single": jumlah_single,
                    "jumlah_rencana_series": jumlah_series,
                    "jumlah_resep": jumlah_resep,
                },
                request=request,
            )

            # Transition status — special audit aksi (tetap log meski status tidak berubah)
            self.audit.log(
                aksi="STATUS_UPDATE" if not is_edit_after_workflow else "EDIT_SOAP_POST_WORKFLOW",
                id_staf=id_staf_dokter,
                tabel_target="kunjungan",
                id_target=payload.id_kunjungan,
                data_lama={"status_antrian": status_lama},
                data_baru={"status_antrian": status_baru, "is_edit": is_edit_after_workflow},
                keterangan=(
                    "Auto-transition setelah dokter input medis selesai."
                    if not is_edit_after_workflow
                    else f"Dokter ubah SOAP saat status {status_lama} (no regression — status tetap)."
                ),
                request=request,
            )

            # ----- 7. COMMIT -----
            self.db.commit()
            self.db.refresh(kunjungan)

            return {
                "status": "success",
                "message": (
                    f"Data SOAP & instruksi medis berhasil disimpan. "
                    f"Pasien diarahkan ke: {status_baru}."
                ),
                "data": {
                    "id_pemeriksaan": id_pemeriksaan_baru,
                    "jumlah_tindakan_single": jumlah_single,
                    "jumlah_rencana_series": jumlah_series,
                    "jumlah_resep": jumlah_resep,
                    "status_kunjungan_baru": status_baru,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal input medis: {str(e)}",
            )

    # =========================================================================
    # SUMMARY DOKTER — dashboard 4 cardbox
    # =========================================================================
    def get_summary_pasien(self, id_pasien: int) -> SummaryDokterResponse:
        """4 cardbox: SOAP / produk dibeli / treatment selesai / foto (placeholder)."""
        # Validasi pasien exists
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )

        soap_rows = self.pemeriksaan_repo.get_riwayat_soap(id_pasien, limit=10)
        produk_rows = self.pemeriksaan_repo.get_produk_dibeli(id_pasien, limit=10)
        treatment_rows = self.pemeriksaan_repo.get_treatment_selesai(id_pasien, limit=10)

        return SummaryDokterResponse(
            cardbox_kiri_atas_soap=[
                SoapRingkasItem(
                    id_pemeriksaan=soap.id_pemeriksaan,
                    # Temuan `created_at`: tanggal KLINIS = kapan pasien datang,
                    # bukan kapan catatannya ditulis (bisa diisi menyusul).
                    tanggal=kj.tgl_kunjungan,
                    nama_dokter=(dokter.nama_staf if dokter else None),
                    ringkasan_anamnesa=_ringkas_teks(soap.anamnesa),
                    ringkasan_diagnosa=_ringkas_teks(soap.diagnosa),
                    full_anamnesa=soap.anamnesa,
                    full_diagnosa=soap.diagnosa,
                )
                for soap, dokter, kj in soap_rows
            ],
            cardbox_kiri_bawah_produk=[
                ProdukDibeliRingkas(
                    tanggal=kj.tgl_kunjungan,
                    nama_produk=prod.nama_produk,
                    qty=resep.qty,
                )
                for resep, prod, kj in produk_rows
            ],
            cardbox_kanan_bawah_treatment=[
                TreatmentSelesaiRingkas(
                    tanggal=kj.tgl_kunjungan,
                    nama_treatment=tr.nama_treatment,
                )
                for tindakan, tr, kj in treatment_rows
            ],
            cardbox_kanan_atas_foto=[],
        )

    # =========================================================================
    # HEADER PASIEN — 3 grid dashboard atas dokter
    # =========================================================================
    def get_header_pasien(self, id_pasien: int) -> HeaderPasienResponse:
        """
        Compose 3 grid header dokter:
        - grid_kiri_identitas: nama + usia + JK + detail hover (no_rm, membership, telp, alamat)
        - grid_tengah_alergi: total + latest + daftar lengkap (alergi aktif saja)
        - grid_kanan_antropometri: data terbaru + BMI/fat%/lean% (via AntropometriService)
        """
        # Reuse pasien_repo.get_by_id with relations (alergi + penyakit_kronis)
        pasien = self.pasien_repo.get_by_id(id_pasien, with_relations=True)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )

        # ----- Grid kiri: identitas -----
        from app.services._clinical_calc import hitung_usia
        usia = hitung_usia(pasien.tgl_lahir)
        jk = (
            pasien.jenis_kelamin.value
            if hasattr(pasien.jenis_kelamin, "value")
            else str(pasien.jenis_kelamin) if pasien.jenis_kelamin else None
        )
        membership = (
            pasien.tipe_membership.value
            if hasattr(pasien.tipe_membership, "value")
            else str(pasien.tipe_membership) if pasien.tipe_membership else None
        )
        grid_kiri = GridIdentitas(
            nama=pasien.nama,
            usia=usia,
            jenis_kelamin=jk,
            detail_hover=DetailHoverIdentitas(
                no_rm=pasien.no_rm,
                membership=membership,
                telepon=pasien.nomor_telepon,
                alamat=pasien.alamat,
            ),
        )

        # ----- Grid tengah: alergi (aktif saja, sorted DESC by id) -----
        alergi_aktif = sorted(
            [a for a in pasien.alergi if a.is_active],
            key=lambda a: a.id_alergi,
            reverse=True,
        )
        daftar_alergi = [
            AlergiRingkasItem(
                id_alergi=a.id_alergi,
                alergen=a.alergen,
                gejala=a.gejala,
                tingkat_keparahan=(
                    a.tingkat_keparahan.value
                    if hasattr(a.tingkat_keparahan, "value")
                    else str(a.tingkat_keparahan) if a.tingkat_keparahan else None
                ),
            )
            for a in alergi_aktif
        ]
        grid_tengah = GridAlergi(
            total_alergi=len(daftar_alergi),
            alergi_display=daftar_alergi[0] if daftar_alergi else None,
            daftar_lengkap=daftar_alergi,
        )

        # ----- Grid kanan: antropometri terakhir + computed -----
        antro_resp = self.antropometri.get_terakhir_with_clinical(id_pasien)
        if antro_resp.has_data:
            grid_kanan = GridAntropometri(
                has_data=True,
                data=AntropometriHeaderData(
                    berat_badan=antro_resp.berat_badan,
                    tinggi_badan=antro_resp.tinggi_badan,
                    bmi=antro_resp.bmi,
                    kategori_bmi=antro_resp.kategori_bmi,
                    fat_percentage=antro_resp.body_fat_pct,
                    lean_percentage=antro_resp.lean_mass_pct,
                    tekanan_darah=antro_resp.tekanan_darah,
                    tgl_ukur=(antro_resp.tgl_ukur.isoformat() if antro_resp.tgl_ukur else None),
                ),
            )
        else:
            grid_kanan = GridAntropometri(has_data=False, data=None)

        return HeaderPasienResponse(
            grid_kiri_identitas=grid_kiri,
            grid_tengah_alergi=grid_tengah,
            grid_kanan_antropometri=grid_kanan,
        )

    # =========================================================================
    # ANTRIAN DOKTER VIEW — dengan filter "yang lewat dokter"
    # =========================================================================
    def lihat_antrian_dokter(self, today=None, id_staf_dokter: Optional[int] = None) -> AntrianDokterResponse:
        """
        Antrian dokter view (per UX spec dr. Hansen).

        SOAP-GUARD scoping (Decision A): kalau id_staf_dokter dipass,
        antrian post-konsul (ANTRI_TREATMENT/ON_TREATMENT/ANTRI_BAYAR/
        ANTRI_OBAT) hanya tampil untuk dokter yang authored SOAP-nya.
        Pasien ANTRI_KONSULTASI/KONSULTASI tetap tampil ke semua dokter
        karena belum ada owner — siap di-claim siapa saja.
        """
        from datetime import date as _date
        if today is None:
            today = _date.today()

        rows = self.kunjungan_repo.list_antrian_dokter_view(
            today=today,
            id_staf_dokter=id_staf_dokter,
        )

        counter_map = {
            "ANTRI_KONSULTASI": 0,
            "KONSULTASI": 0,
            "ANTRI_TREATMENT": 0,
            "ON_TREATMENT": 0,
            "ANTRI_BAYAR": 0,
            "ANTRI_OBAT": 0,
        }

        items = []
        for kunjungan, pasien, sudah_konsultasi in rows:
            status_v = kunjungan.status_antrian or ""
            if status_v in counter_map:
                counter_map[status_v] += 1

            jk = (
                pasien.jenis_kelamin.value
                if hasattr(pasien.jenis_kelamin, "value")
                else (str(pasien.jenis_kelamin) if pasien.jenis_kelamin else None)
            )
            items.append(AntrianDokterItem(
                id_kunjungan=kunjungan.id_kunjungan,
                nomor_antrean=kunjungan.nomor_antrean,
                status_antrian=kunjungan.status_antrian,
                tgl_kunjungan=kunjungan.tgl_kunjungan,
                keluhan_utama=kunjungan.keluhan_utama,
                id_pasien=pasien.id_pasien,
                no_rm=pasien.no_rm,
                nama_pasien=pasien.nama,
                jenis_kelamin=jk,
                sudah_konsultasi=sudah_konsultasi,
            ))

        counter = CounterStatusAntrian(
            menunggu_konsultasi=counter_map.get("ANTRI_KONSULTASI", 0),
            sedang_konsultasi=counter_map.get("KONSULTASI", 0),
            antri_treatment=counter_map.get("ANTRI_TREATMENT", 0),
            sedang_treatment=counter_map.get("ON_TREATMENT", 0),
            antri_bayar=counter_map.get("ANTRI_BAYAR", 0),
            antri_obat=counter_map.get("ANTRI_OBAT", 0),
        )

        return AntrianDokterResponse(
            tanggal=today,
            total=len(items),
            counter=counter,
            data=items,
        )


__all__ = ["PemeriksaanService"]
