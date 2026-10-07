"""
PasienService — business logic untuk pasien.

Audit log:
- register_pasien_baru: CREATE pasien + CREATE kunjungan
- tambah_alergi: CREATE alergi
- hapus_alergi: DELETE (soft) alergi

PII handling:
- nomor_ktp & alamat & tgl_lahir TIDAK di-log raw di audit
  (catat hash/truncated atau hanya nama+no_rm)
"""

from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan, KunjunganAntropometri, Pasien,
    PasienAlergi, PasienPenyakitKronis,
)
from app.core.nik import normalisasi_nik
from app.core.no_rm_omnicare import NoRmOmnicareTidakSah, normalisasi_no_rm_omnicare
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.pasien_repo import PasienRepository
from app.schemas.pasien import (
    AlergiAddRequest, AlergiResponse, KunjunganRingkasItem,
    PasienBaruRequest, PasienDetailResponse, PasienResponse,
    RiwayatPasienResponse, RiwayatProdukResepItem,
    RiwayatProdukTerbayarItem, RiwayatTindakanDiresepkanItem,
    RiwayatTreatmentItem,
)
from app.services.audit_service import AuditService


class DuplikatPasienError(Exception):
    """Duplikat pasien terdeteksi saat registrasi.

    kind = "nik"  -> NIK/KTP sama persis (BLOK keras, tak bisa override).
    kind = "soft" -> nama+jenis_kelamin+tgl_lahir sama (peringatan; bisa lanjut
                     dgn konfirmasi_duplikat=True).
    candidates    -> list[Pasien] yang cocok.
    """

    def __init__(self, kind: str, candidates: list):
        self.kind = kind
        self.candidates = candidates or []
        super().__init__(f"Duplikat pasien terdeteksi ({kind})")


class PasienService:
    def __init__(self, db: Session):
        self.db = db
        self.pasien_repo = PasienRepository(db)
        self.kunjungan_repo = KunjunganRepository(db)
        self.audit = AuditService(db)

    def _validate_tier_active(self, tier_value):
        """#362C - Validate tipe_membership match tier aktif di master_membership.
        REGULAR selalu boleh (fast path, no DB query).
        """
        from app.db.models import MasterMembership
        from sqlalchemy import select
        if tier_value is None:
            return
        tier_str = tier_value.value if hasattr(tier_value, "value") else str(tier_value)
        if tier_str.upper() == "REGULAR":
            return
        # Cek master_membership aktif
        stmt = (
            select(MasterMembership)
            .where(MasterMembership.nama_tier == tier_str)
            .where(MasterMembership.is_active.is_(True))
            .limit(1)
        )
        tier = self.db.execute(stmt).scalar_one_or_none()
        if tier is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tier '{tier_str}' tidak aktif di Master Membership atau belum ada. "
                    f"Aktivasi tier dulu di Master Data > Membership."
                ),
            )

    @staticmethod
    def _norm_nama(nama: str) -> str:
        """Normalisasi nama utk banding: huruf kecil + spasi ganda diringkas."""
        return " ".join((nama or "").split()).lower()

    def find_duplicate_candidates(self, nama, jenis_kelamin, tgl_lahir, nomor_ktp, exclude_id=None):
        """Return (nik_match | None, soft_matches: list[Pasien]).

        nik_match  : NIK/KTP sama persis (non-kosong) -> blok keras.
        soft_matches: nama(normalisasi) + jenis_kelamin + tgl_lahir sama -> peringatan.
        """
        # Lewat normalisasi_nik: '0'/'-'/spasi berarti "tidak ada", BUKAN nilai
        # yang bisa bertabrakan. Tanpa ini, pasien kedua tanpa KTP ditolak.
        nik = normalisasi_nik(nomor_ktp)
        nik_match = None
        if nik:
            cand = self.pasien_repo.find_by_nik(nik)
            if cand is not None and cand.id_pasien != exclude_id:
                nik_match = cand
        soft = []
        if tgl_lahir is not None:
            target = self._norm_nama(nama)
            for cand in self.pasien_repo.find_by_dob_gender(tgl_lahir, jenis_kelamin):
                if cand.id_pasien == exclude_id:
                    continue
                if self._norm_nama(cand.nama) == target:
                    soft.append(cand)
        return nik_match, soft

    def _cek_no_rm_omnicare(self, raw, id_pasien_sendiri: Optional[int] = None) -> Optional[str]:
        """Bakukan + pastikan belum dipegang pasien LAIN (aktif maupun nonaktif).
        400 bila bentuknya salah, 409 bila sudah dipakai — pesannya menyebut pemiliknya
        supaya staf bisa memeriksa siapa yang benar."""
        try:
            nomor = normalisasi_no_rm_omnicare(raw)
        except NoRmOmnicareTidakSah as e:
            raise HTTPException(status_code=400, detail=str(e))
        if nomor:
            lain = self.pasien_repo.find_by_no_rm_omnicare(nomor)
            if lain is not None and lain.id_pasien != id_pasien_sendiri:
                ket = "" if lain.is_active else " — pasien NONAKTIF; kalau orangnya sama, pakai Gabungkan Pasien"
                raise HTTPException(status_code=409, detail=(
                    f"No. RM Omnicare {nomor} sudah dipakai {lain.nama} "
                    f"(RM Sehati {lain.no_rm}){ket}. Lihat nomor tertinggi di Cari Pasien."))
        return nomor

    @staticmethod
    def _bentrok_omnicare(e: Exception) -> bool:
        """IntegrityError dari unique index nomor Omnicare (dua pendaftaran bersamaan
        dengan nomor yang sama). Dicocokkan per NAMA indeks — pelajaran Temuan 34:
        `except IntegrityError` generik bisa memberi pesan yang berbohong."""
        return "ux_pasien_no_rm_omnicare" in str(e)

    def terbaru(self, limit: int = 10) -> list[PasienResponse]:
        return [PasienResponse.model_validate(p) for p in self.pasien_repo.terbaru(limit)]

    def rm_omnicare_tertinggi(self) -> dict:
        return self.pasien_repo.rm_omnicare_tertinggi()

    def register_pasien_baru(self, payload: PasienBaruRequest, id_staf_fo: int, request: Optional[Request] = None, buat_kunjungan: bool = True, konfirmasi_duplikat: bool = False) -> dict:
        no_rm_omnicare = self._cek_no_rm_omnicare(payload.no_rm_omnicare)
        # ---- Deteksi duplikat (SEBELUM membuat apa pun) ----
        nik_match, soft_matches = self.find_duplicate_candidates(
            payload.nama, payload.jenis_kelamin, payload.tgl_lahir, payload.nomor_ktp
        )
        if nik_match is not None:
            raise DuplikatPasienError(kind="nik", candidates=[nik_match])
        if not konfirmasi_duplikat and soft_matches:
            raise DuplikatPasienError(kind="soft", candidates=soft_matches)

        try:
            # #362C - Validate tier aktif sebelum register
            self._validate_tier_active(payload.tipe_membership)
            no_rm_baru = self.pasien_repo.generate_next_no_rm()
            pasien = Pasien(
                no_rm=no_rm_baru, nama=payload.nama, jenis_kelamin=payload.jenis_kelamin,
                alamat=payload.alamat or None, tgl_lahir=payload.tgl_lahir,
                nomor_telepon=payload.nomor_telepon or None,
                nomor_ktp=normalisasi_nik(payload.nomor_ktp),
                no_rm_omnicare=no_rm_omnicare,
                email_address=payload.email_address or None, sumber_referensi=payload.sumber_referensi or None,
                tipe_membership=(getattr(payload.tipe_membership, "value", payload.tipe_membership) or "REGULAR"), id_staf=id_staf_fo,
            )
            self.pasien_repo.create(pasien)
            id_pasien_baru = pasien.id_pasien

            # #362E - Tier diset di pasien table tapi TIDAK auto-create pending history.
            # User harus klik "Kelola Membership" di Detail Pasien untuk aktivasi.
            # Ini supaya consistent dengan flow renewal/upgrade (semua via section).

            for item in payload.alergi:
                self.pasien_repo.add_alergi(PasienAlergi(
                    id_pasien=id_pasien_baru, alergen=item.alergen,
                    gejala=item.gejala or None, tingkat_keparahan=item.tingkat_keparahan,
                    id_staf=id_staf_fo,
                ))

            for item in payload.penyakit_kronis:
                self.pasien_repo.add_penyakit_kronis(PasienPenyakitKronis(
                    id_pasien=id_pasien_baru, nama_penyakit=item.nama_penyakit,
                    catatan=item.catatan or None,
                ))

            # buat_kunjungan=False → simpan pasien SAJA tanpa antrian (pre-registrasi).
            id_kunjungan_baru = None
            nomor_antrean = None
            kunjungan = None
            if buat_kunjungan:
                nomor_antrean = self.kunjungan_repo.get_nomor_antrian_berikutnya()
                kunjungan = Kunjungan(
                    id_pasien=id_pasien_baru, status_antrian=payload.status_antrian,
                    keluhan_utama=payload.keluhan_utama or None, id_staf_fo=id_staf_fo,
                    nomor_antrean=nomor_antrean, sumber_pendaftaran="WALK_IN",
                    # FO-ASSIGN-DOKTER (Task #329): propagate assignment kalau ada
                    id_staf_dokter_assigned=payload.id_staf_dokter_assigned,
                )
                self.kunjungan_repo.create(kunjungan)
                id_kunjungan_baru = kunjungan.id_kunjungan

            if buat_kunjungan and payload.antropometri:
                self.kunjungan_repo.add_antropometri(KunjunganAntropometri(
                    id_kunjungan=id_kunjungan_baru,
                    berat_badan=payload.antropometri.berat_badan,
                    tinggi_badan=payload.antropometri.tinggi_badan,
                    tekanan_darah=payload.antropometri.tekanan_darah or None,
                    suhu_tubuh=payload.antropometri.suhu_tubuh,
                    skinfold_titik_1=payload.antropometri.skinfold_titik_1,
                    skinfold_titik_2=payload.antropometri.skinfold_titik_2,
                    skinfold_titik_3=payload.antropometri.skinfold_titik_3,
                    lingkar_perut=payload.antropometri.lingkar_perut,
                    id_staf=id_staf_fo,
                ))

            # AUDIT — TIDAK log PII (nomor_ktp, alamat, tgl_lahir lengkap)
            self.audit.log_create(
                id_staf=id_staf_fo,
                tabel="pasien",
                id_target=id_pasien_baru,
                data_baru={
                    "no_rm": no_rm_baru,
                    "no_rm_omnicare": no_rm_omnicare,
                    "nama": payload.nama,
                    "jenis_kelamin": payload.jenis_kelamin.value if hasattr(payload.jenis_kelamin, 'value') else str(payload.jenis_kelamin),
                    "tipe_membership": payload.tipe_membership.value if hasattr(payload.tipe_membership, 'value') else str(payload.tipe_membership),
                    "punya_alergi": len(payload.alergi) > 0,
                    "punya_penyakit_kronis": len(payload.penyakit_kronis) > 0,
                    "punya_antropometri": bool(buat_kunjungan and payload.antropometri),
                },
                request=request,
            )
            if buat_kunjungan:
                self.audit.log_create(
                    id_staf=id_staf_fo,
                    tabel="kunjungan",
                    id_target=id_kunjungan_baru,
                    data_baru={
                        "id_pasien": id_pasien_baru,
                        "nomor_antrean": nomor_antrean,
                        "status_antrian": payload.status_antrian,
                        "sumber_pendaftaran": "WALK_IN",
                    },
                    request=request,
                )

            self.db.commit()
            self.db.refresh(pasien)
            if kunjungan is not None:
                self.db.refresh(kunjungan)
            return {
                "status": "success",
                "message": f"Data lengkap pasien baru '{payload.nama}' berhasil disimpan.",
                "data": {"no_rm": no_rm_baru, "id_pasien": id_pasien_baru, "id_kunjungan": id_kunjungan_baru, "nomor_antrean": nomor_antrean},
            }
        except HTTPException:
            # Preserve specific HTTPException (mis. 400 tier nonaktif) — don't swallow as 500
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            if self._bentrok_omnicare(e):
                raise HTTPException(status_code=409, detail=(
                    f"No. RM Omnicare {no_rm_omnicare} baru saja dipakai pendaftaran lain. "
                    f"Lihat nomor tertinggi di Cari Pasien lalu coba lagi."))
            raise HTTPException(status_code=500, detail=f"Gagal register pasien: {str(e)}")

    def search(self, keyword: str, limit: int = 50) -> list[PasienResponse]:
        if not keyword.strip():
            return []
        return [PasienResponse.model_validate(p) for p in self.pasien_repo.search(keyword.strip(), limit=limit)]

    def get_by_id(self, id_pasien: int) -> PasienResponse:
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(status_code=404, detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.")
        return PasienResponse.model_validate(pasien)

    def get_detail(self, id_pasien: int) -> PasienDetailResponse:
        pasien = self.pasien_repo.get_by_id(id_pasien, with_relations=True)
        if pasien is None:
            raise HTTPException(status_code=404, detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.")
        alergi_aktif = [a for a in pasien.alergi if a.is_active]
        penyakit_aktif = [p for p in pasien.penyakit_kronis if p.is_active]
        return PasienDetailResponse(
            **PasienResponse.model_validate(pasien).model_dump(),
            alergi=[AlergiResponse.model_validate(a) for a in alergi_aktif],
            penyakit_kronis=[
                {"id_penyakit": p.id_penyakit, "nama_penyakit": p.nama_penyakit, "kode_penyakit": p.kode_penyakit, "catatan": p.catatan, "is_active": p.is_active}
                for p in penyakit_aktif
            ],
        )

    def get_riwayat(self, id_pasien: int, limit_kunjungan: int = 20) -> RiwayatPasienResponse:
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(status_code=404, detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.")
        kunjungan_list = self.pasien_repo.get_ringkasan_kunjungan(id_pasien=id_pasien, limit=limit_kunjungan)
        treatment_list = self.pasien_repo.get_riwayat_treatment(id_pasien)
        tindakan_resep_rows = self.pasien_repo.get_riwayat_tindakan_diresepkan(id_pasien)
        produk_resep_rows = self.pasien_repo.get_riwayat_produk_resep(id_pasien)
        produk_terbayar_rows = self.pasien_repo.get_riwayat_produk_terbayar(id_pasien)
        return RiwayatPasienResponse(
            info_pasien=PasienResponse.model_validate(pasien),
            total_kunjungan=len(kunjungan_list),
            kunjungan=[KunjunganRingkasItem.model_validate(k) for k in kunjungan_list],
            riwayat_treatment=[
                RiwayatTreatmentItem(
                    id_rencana=t.id_rencana, urutan_sesi=t.urutan_sesi, nama_tindakan=t.nama_tindakan,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    tgl_target_mulai=t.tgl_target_mulai, tgl_target_akhir=t.tgl_target_akhir,
                    tgl_eksekusi=t.tgl_eksekusi, catatan_dokter=t.catatan_dokter, created_at=t.created_at,
                ) for t in treatment_list
            ],
            riwayat_tindakan_diresepkan=[
                RiwayatTindakanDiresepkanItem(
                    id_kunjungan_tindakan=tindakan.id_kunjungan_tindakan,
                    id_kunjungan=tindakan.id_kunjungan,
                    tgl_diresepkan=kj.tgl_kunjungan,
                    nama_treatment=tr.nama_treatment,
                    harga=float(tr.harga) if tr.harga else 0.0,
                    status_tindakan=(
                        tindakan.status_tindakan.value
                        if tindakan.status_tindakan and hasattr(tindakan.status_tindakan, "value")
                        else (str(tindakan.status_tindakan) if tindakan.status_tindakan else None)
                    ),
                ) for tindakan, tr, kj in tindakan_resep_rows
            ],
            produk_diresepkan=[
                RiwayatProdukResepItem(
                    id_resep=resep.id_resep, id_kunjungan=resep.id_kunjungan, tgl_resep=kj.tgl_kunjungan,
                    nama_produk=prod.nama_produk, qty=resep.qty, aturan_pakai=resep.aturan_pakai,
                    status_item=(resep.status_item.value if hasattr(resep.status_item, "value") else (str(resep.status_item) if resep.status_item else None)),
                ) for resep, prod, kj in produk_resep_rows
            ],
            produk_terbayar=[
                RiwayatProdukTerbayarItem(
                    id_detail=det.id_detail, id_transaksi=det.id_transaksi, tgl_bayar=trx.waktu_bayar,
                    nama_produk=prod.nama_produk, qty=det.qty,
                    harga_satuan=float(det.harga_satuan), subtotal=float(det.subtotal),
                ) for det, prod, trx in produk_terbayar_rows
            ],
        )

    def update_pasien_profile(
        self,
        id_pasien: int,
        payload,  # PasienUpdateRequest
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> dict:
        """TODO-NEW-6 #50 - Edit profile pasien existing (partial update).

        PII handling: alamat, tgl_lahir, nomor_ktp masuk audit log dalam
        bentuk redacted (no_rm + nama only). Detail value tetap tersimpan
        di pasien table tapi tidak diteruskan ke audit_log raw.
        """
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=404,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )
        # Snapshot data lama (untuk audit — non-PII only)
        data_lama = {
            "no_rm": pasien.no_rm,
            "nama": pasien.nama,
        }
        # Track field yang di-update (untuk audit message — tanpa value raw)
        fields_changed: list = []
        try:
            data_baru_audit = {"no_rm": pasien.no_rm}
            if payload.nama is not None and payload.nama.strip():
                pasien.nama = payload.nama.strip()
                data_baru_audit["nama"] = pasien.nama
                fields_changed.append("nama")
            if payload.jenis_kelamin is not None:
                pasien.jenis_kelamin = payload.jenis_kelamin
                data_baru_audit["jenis_kelamin"] = (
                    payload.jenis_kelamin.value
                    if hasattr(payload.jenis_kelamin, "value")
                    else str(payload.jenis_kelamin)
                )
                fields_changed.append("jenis_kelamin")
            if payload.tgl_lahir is not None:
                pasien.tgl_lahir = payload.tgl_lahir
                # Audit log YEAR only (no raw birth date — PII)
                data_baru_audit["tgl_lahir_year"] = payload.tgl_lahir.year
                fields_changed.append("tgl_lahir")
            if payload.alamat is not None:
                pasien.alamat = (payload.alamat or "").strip() or None
                # Audit log: indicate change occurred, NOT raw alamat (PII)
                data_baru_audit["alamat_changed"] = True
                fields_changed.append("alamat")
            if payload.nomor_telepon is not None:
                pasien.nomor_telepon = (payload.nomor_telepon or "").strip() or None
                # Audit last 4 only
                tel = pasien.nomor_telepon or ""
                data_baru_audit["nomor_telepon_last4"] = tel[-4:] if len(tel) >= 4 else "***"
                fields_changed.append("nomor_telepon")
            if payload.nomor_ktp is not None:
                _new_nik = normalisasi_nik(payload.nomor_ktp)
                if _new_nik:
                    _other = self.pasien_repo.find_by_nik(_new_nik)
                    if _other is not None and _other.id_pasien != id_pasien:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"NIK sudah terdaftar atas pasien lain "
                                f"(RM {_other.no_rm}, {_other.nama}). "
                                f"Perbaiki data yang benar, jangan buat duplikat."
                            ),
                        )
                pasien.nomor_ktp = _new_nik
                # Audit: KTP NEVER logged raw — just flag change occurred
                data_baru_audit["nomor_ktp_changed"] = True
                fields_changed.append("nomor_ktp")
            if payload.no_rm_omnicare is not None:
                _omni = self._cek_no_rm_omnicare(payload.no_rm_omnicare, id_pasien)
                if _omni != pasien.no_rm_omnicare:
                    data_lama["no_rm_omnicare"] = pasien.no_rm_omnicare
                    pasien.no_rm_omnicare = _omni
                    data_baru_audit["no_rm_omnicare"] = _omni
                    fields_changed.append("no_rm_omnicare")
            if payload.email_address is not None:
                pasien.email_address = (payload.email_address or "").strip() or None
                data_baru_audit["email_address"] = pasien.email_address
                fields_changed.append("email_address")
            if payload.sumber_referensi is not None:
                pasien.sumber_referensi = (payload.sumber_referensi or "").strip() or None
                data_baru_audit["sumber_referensi"] = pasien.sumber_referensi
                fields_changed.append("sumber_referensi")
            # #362E - tipe_membership tidak di-handle disini. Use section Membership.
            # (Form edit pasien template juga sudah hapus dropdown tier)
            if not fields_changed:
                return {"status": "no_change", "id_pasien": id_pasien}
            data_baru_audit["fields_changed"] = ",".join(fields_changed)
            self.db.flush()
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="pasien",
                id_target=id_pasien,
                data_lama=data_lama,
                data_baru=data_baru_audit,
                request=request,
            )
            self.db.commit()
            return {
                "status": "success",
                "id_pasien": id_pasien,
                "fields_changed": fields_changed,
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            if self._bentrok_omnicare(e):
                raise HTTPException(status_code=409, detail=(
                    "No. RM Omnicare itu baru saja dipakai pasien lain. "
                    "Lihat nomor tertinggi di Cari Pasien lalu coba lagi."))
            raise HTTPException(
                status_code=500,
                detail=f"Gagal update profile pasien: {str(e)}",
            )

    def tambah_alergi(self, payload: AlergiAddRequest, id_staf: int, request: Optional[Request] = None) -> AlergiResponse:
        pasien = self.pasien_repo.get_by_id(payload.id_pasien)
        if pasien is None:
            raise HTTPException(status_code=404, detail=f"Pasien dengan ID {payload.id_pasien} tidak ditemukan.")
        try:
            alergi = PasienAlergi(
                id_pasien=payload.id_pasien, alergen=payload.alergen,
                gejala=payload.gejala or None, tingkat_keparahan=payload.tingkat_keparahan,
                id_staf=id_staf,
            )
            self.pasien_repo.add_alergi(alergi)
            self.audit.log_create(
                id_staf=id_staf,
                tabel="pasien_alergi",
                id_target=alergi.id_alergi,
                data_baru={
                    "id_pasien": payload.id_pasien,
                    "alergen": payload.alergen,
                    "tingkat_keparahan": payload.tingkat_keparahan.value if hasattr(payload.tingkat_keparahan, "value") else str(payload.tingkat_keparahan),
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(alergi)
            return AlergiResponse.model_validate(alergi)
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal tambah alergi: {str(e)}")

    def update_alergi(
        self,
        id_alergi: int,
        payload,  # AlergiUpdateRequest
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> "AlergiResponse":
        """TODO-NEW-1 #29A - Edit alergi existing entry (partial update)."""
        alergi = self.db.get(PasienAlergi, id_alergi)
        if alergi is None:
            raise HTTPException(
                status_code=404,
                detail=f"Alergi dengan ID {id_alergi} tidak ditemukan.",
            )
        if not alergi.is_active:
            raise HTTPException(
                status_code=400,
                detail="Alergi sudah di-nonaktifkan. Tidak bisa di-edit.",
            )
        data_lama = {
            "alergen": alergi.alergen,
            "gejala": alergi.gejala,
            "tingkat_keparahan": (
                alergi.tingkat_keparahan.value
                if hasattr(alergi.tingkat_keparahan, "value")
                else str(alergi.tingkat_keparahan)
            ),
        }
        try:
            data_baru_audit = {}
            if payload.alergen is not None and payload.alergen.strip():
                alergi.alergen = payload.alergen.strip()
                data_baru_audit["alergen"] = alergi.alergen
            if payload.gejala is not None:
                alergi.gejala = (payload.gejala or "").strip() or None
                data_baru_audit["gejala"] = alergi.gejala
            if payload.tingkat_keparahan is not None:
                alergi.tingkat_keparahan = payload.tingkat_keparahan
                data_baru_audit["tingkat_keparahan"] = (
                    payload.tingkat_keparahan.value
                    if hasattr(payload.tingkat_keparahan, "value")
                    else str(payload.tingkat_keparahan)
                )
            if not data_baru_audit:
                return AlergiResponse.model_validate(alergi)
            self.db.flush()
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="pasien_alergi",
                id_target=id_alergi,
                data_lama=data_lama,
                data_baru=data_baru_audit,
                request=request,
            )
            self.db.commit()
            self.db.refresh(alergi)
            return AlergiResponse.model_validate(alergi)
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Gagal update alergi: {str(e)}",
            )

    def hapus_alergi(self, id_alergi: int, actor_id_staf: Optional[int] = None, request: Optional[Request] = None) -> dict:
        alergi = self.db.get(PasienAlergi, id_alergi)
        if alergi is None:
            raise HTTPException(status_code=404, detail=f"Alergi dengan ID {id_alergi} tidak ditemukan.")
        snapshot_lama = {
            "id_alergi": alergi.id_alergi,
            "id_pasien": alergi.id_pasien,
            "alergen": alergi.alergen,
            "is_active_lama": alergi.is_active,
        }
        try:
            ok = self.pasien_repo.soft_delete_alergi(id_alergi)
            if not ok:
                raise HTTPException(status_code=500, detail="Gagal soft delete alergi.")
            self.audit.log_delete(
                id_staf=actor_id_staf,
                tabel="pasien_alergi",
                id_target=id_alergi,
                data_lama=snapshot_lama,
                request=request,
            )
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Gagal register pasien: {e!s}")


    def tambah_penyakit_kronis(self, payload, id_staf: int, request=None):
        """TODO-NEW-1 #29B - Tambah penyakit kronis ke pasien existing."""
        pasien = self.pasien_repo.get_by_id(payload.id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=404,
                detail=f"Pasien dengan ID {payload.id_pasien} tidak ditemukan.",
            )
        try:
            penyakit = PasienPenyakitKronis(
                id_pasien=payload.id_pasien,
                nama_penyakit=payload.nama_penyakit,
                catatan=(payload.catatan or "").strip() or None,
            )
            self.pasien_repo.add_penyakit_kronis(penyakit)
            self.audit.log_create(
                id_staf=id_staf,
                tabel="pasien_penyakit_kronis",
                id_target=penyakit.id_penyakit,
                data_baru={
                    "id_pasien": payload.id_pasien,
                    "nama_penyakit": payload.nama_penyakit,
                    "catatan": penyakit.catatan,
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(penyakit)
            return penyakit
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Gagal tambah penyakit kronis: {str(e)}",
            )

    def update_penyakit_kronis(self, id_penyakit: int, payload, actor_id_staf: int, request=None):
        """TODO-NEW-1 #29B - Edit penyakit kronis existing (partial update)."""
        penyakit = self.db.get(PasienPenyakitKronis, id_penyakit)
        if penyakit is None:
            raise HTTPException(
                status_code=404,
                detail=f"Penyakit kronis dengan ID {id_penyakit} tidak ditemukan.",
            )
        if not penyakit.is_active:
            raise HTTPException(
                status_code=400,
                detail="Penyakit kronis sudah di-nonaktifkan. Tidak bisa di-edit.",
            )
        data_lama = {
            "nama_penyakit": penyakit.nama_penyakit,
            "catatan": penyakit.catatan,
        }
        try:
            data_baru_audit = {}
            if payload.nama_penyakit is not None and payload.nama_penyakit.strip():
                penyakit.nama_penyakit = payload.nama_penyakit.strip()
                data_baru_audit["nama_penyakit"] = penyakit.nama_penyakit
            if payload.catatan is not None:
                penyakit.catatan = (payload.catatan or "").strip() or None
                data_baru_audit["catatan"] = penyakit.catatan
            if not data_baru_audit:
                return penyakit
            self.db.flush()
            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="pasien_penyakit_kronis",
                id_target=id_penyakit,
                data_lama=data_lama,
                data_baru=data_baru_audit,
                request=request,
            )
            self.db.commit()
            self.db.refresh(penyakit)
            return penyakit
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Gagal update penyakit kronis: {str(e)}",
            )

    def hapus_penyakit_kronis(self, id_penyakit: int, actor_id_staf=None, request=None):
        """TODO-NEW-1 #29B - Soft delete penyakit kronis."""
        penyakit = self.db.get(PasienPenyakitKronis, id_penyakit)
        if penyakit is None:
            raise HTTPException(
                status_code=404,
                detail=f"Penyakit kronis dengan ID {id_penyakit} tidak ditemukan.",
            )
        snapshot_lama = {
            "id_penyakit": penyakit.id_penyakit,
            "id_pasien": penyakit.id_pasien,
            "nama_penyakit": penyakit.nama_penyakit,
            "is_active_lama": penyakit.is_active,
        }
        try:
            ok = self.pasien_repo.soft_delete_penyakit_kronis(id_penyakit)
            if not ok:
                raise HTTPException(
                    status_code=500,
                    detail="Gagal soft delete penyakit kronis.",
                )
            self.audit.log_delete(
                id_staf=actor_id_staf,
                tabel="pasien_penyakit_kronis",
                id_target=id_penyakit,
                data_lama=snapshot_lama,
                request=request,
            )
            self.db.commit()
            return {"status": "success", "id_penyakit": id_penyakit}
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Gagal hapus penyakit kronis: {str(e)}",
            )


__all__ = ["PasienService"]
