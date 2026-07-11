"""
KunjunganService — business logic untuk kunjungan, antrian, & status flow.

Alur normal antrian:
    ANTRI_KONSULTASI → KONSULTASI → ANTRI_TREATMENT → ON_TREATMENT →
    ANTRI_BAYAR → ANTRI_OBAT → COMPLETED

BATAL bisa dari status apa pun (tapi ada role guard di endpoint).
"""

from datetime import date
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganAntropometri,
    Pasien,
    StatusAntrianEnum,
)
from app.repositories.kunjungan_repo import KunjunganRepository
from app.repositories.pasien_repo import PasienRepository
from app.schemas.kunjungan import (
    AntrianHariIniResponse,
    KunjunganAntrianItem,
    KunjunganDetailResponse,
    KunjunganLamaRequest,
)
from app.services.audit_service import AuditService


# =============================================================================
# Valid status transitions — alur normal
# =============================================================================
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "ANTRI_KONSULTASI": {"KONSULTASI", "BATAL"},
    "KONSULTASI": {"ANTRI_TREATMENT", "ANTRI_BAYAR", "ANTRI_OBAT", "BATAL"},
    "ANTRI_TREATMENT": {"ON_TREATMENT", "BATAL"},
    "ON_TREATMENT": {"ANTRI_BAYAR", "ANTRI_OBAT", "COMPLETED", "BATAL"},
    "ANTRI_BAYAR": {"ANTRI_OBAT", "COMPLETED", "BATAL"},
    "ANTRI_OBAT": {"COMPLETED", "BATAL"},
    "COMPLETED": set(),
    "BATAL": set(),
}


class KunjunganService:
    """Service untuk semua operasi kunjungan."""

    def __init__(self, db: Session):
        self.db = db
        self.kunjungan_repo = KunjunganRepository(db)
        self.pasien_repo = PasienRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # KUNJUNGAN LAMA — pasien existing, daftar untuk kunjungan baru
    # =========================================================================
    def kunjungan_lama(
        self,
        payload: KunjunganLamaRequest,
        id_staf_fo: int,
        request: Optional[Request] = None,
    ) -> dict:
        """Pasien existing daftar untuk kunjungan baru hari ini."""
        # 1. Validasi pasien exists
        pasien = self.pasien_repo.get_by_id(payload.id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {payload.id_pasien} tidak ditemukan.",
            )

        # 1b. Guard duplicate — pasien sama tidak boleh diantrikan 2x hari ini
        existing = self.kunjungan_repo.get_active_kunjungan_today(payload.id_pasien)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Pasien '{pasien.nama}' sudah ada di antrian hari ini "
                    f"(no.antrean #{existing.nomor_antrean}, status "
                    f"{existing.status_antrian}). Tidak boleh daftar 2x. "
                    f"Pakai tombol Ubah/Batal di halaman antrian kalau perlu koreksi."
                ),
            )

        try:
            nomor_antrean = self.kunjungan_repo.get_nomor_antrian_berikutnya()
            kunjungan = Kunjungan(
                id_pasien=payload.id_pasien,
                status_antrian=payload.status_antrian,
                keluhan_utama=payload.keluhan_utama or None,
                id_staf_fo=id_staf_fo,
                nomor_antrean=nomor_antrean,
                sumber_pendaftaran=payload.sumber_pendaftaran,
                # FO-ASSIGN-DOKTER (Task #329): propagate assignment kalau ada
                id_staf_dokter_assigned=payload.id_staf_dokter_assigned,
            )
            self.kunjungan_repo.create(kunjungan)
            id_kunjungan_baru = kunjungan.id_kunjungan

            if payload.antropometri:
                antro = KunjunganAntropometri(
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
                )
                self.kunjungan_repo.add_antropometri(antro)

            self.audit.log_create(
                id_staf=id_staf_fo,
                tabel="kunjungan",
                id_target=id_kunjungan_baru,
                data_baru={
                    "id_pasien": payload.id_pasien,
                    "nomor_antrean": nomor_antrean,
                    "status_antrian": payload.status_antrian,
                    "sumber_pendaftaran": payload.sumber_pendaftaran,
                    "punya_antropometri": payload.antropometri is not None,
                },
                request=request,
            )

            self.db.commit()
            self.db.refresh(kunjungan)

            return {
                "status": "success",
                "message": f"Kunjungan baru untuk '{pasien.nama}' berhasil dibuat.",
                "data": {
                    "id_kunjungan": kunjungan.id_kunjungan,
                    "nomor_antrean": nomor_antrean,
                    "id_pasien": payload.id_pasien,
                    "status_antrian": payload.status_antrian,
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal buat kunjungan: {e!s}",
            )

    # =========================================================================
    # LIHAT ANTRIAN HARI INI
    # =========================================================================
    def lihat_antrian_hari_ini(
        self,
        exclude_completed: bool = True,
        today: Optional[date] = None,
    ) -> AntrianHariIniResponse:
        """List semua antrian hari ini, urut by nomor_antrean."""
        if today is None:
            today = date.today()

        active_statuses = [
            "ANTRI_KONSULTASI",
            "KONSULTASI",
            "ANTRI_TREATMENT",
            "ON_TREATMENT",
            "ANTRI_BAYAR",
            "ANTRI_OBAT",
        ]
        status_filter = active_statuses if exclude_completed else None

        rows = self.kunjungan_repo.list_antrian_hari_ini_with_pasien(
            today=today,
            status_filter=status_filter,
        )

        items = [
            KunjunganAntrianItem(
                id_kunjungan=k.id_kunjungan,
                nomor_antrean=k.nomor_antrean,
                status_antrian=k.status_antrian,
                keluhan_utama=k.keluhan_utama,
                tgl_kunjungan=k.tgl_kunjungan,
                sumber_pendaftaran=k.sumber_pendaftaran,
                waktu_masuk_status=k.waktu_masuk_status,
                id_pasien=p.id_pasien,
                no_rm=p.no_rm,
                nama_pasien=p.nama,
                jenis_kelamin=p.jenis_kelamin,
                tgl_lahir=p.tgl_lahir,
                tipe_membership=p.tipe_membership,
                # FO-ASSIGN-DOKTER #329 FIX-1
                id_staf_dokter_assigned=k.id_staf_dokter_assigned,
                dokter_dituju_nama=dokter_nama,
            )
            for k, p, dokter_nama in rows
        ]

        return AntrianHariIniResponse(
            tanggal=today,
            total=len(items),
            data=items,
        )

    # =========================================================================
    # DETAIL KUNJUNGAN
    # =========================================================================
    def get_detail(self, id_kunjungan: int) -> KunjunganDetailResponse:
        """Detail 1 kunjungan + nama pasien. Raise 404 kalau tidak ada."""
        row = self.kunjungan_repo.get_with_pasien(id_kunjungan)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan dengan ID {id_kunjungan} tidak ditemukan.",
            )
        k, p = row
        return KunjunganDetailResponse(
            id_kunjungan=k.id_kunjungan,
            nomor_antrean=k.nomor_antrean,
            status_antrian=k.status_antrian,
            keluhan_utama=k.keluhan_utama,
            tgl_kunjungan=k.tgl_kunjungan,
            sumber_pendaftaran=k.sumber_pendaftaran,
            id_pasien=p.id_pasien,
            no_rm=p.no_rm,
            nama_pasien=p.nama,
        )

    # =========================================================================
    # UBAH STATUS — state machine enforcement
    # =========================================================================
    # =========================================================================
    # UBAH DOKTER ASSIGNED (FO-ASSIGN-DOKTER #329 FIX-2)
    # =========================================================================
    def ubah_dokter_assigned(
        self,
        id_kunjungan: int,
        id_staf_dokter_assigned: Optional[int],
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> dict:
        """
        Reassign dokter dituju TANPA mengubah status_antrian.
        - id_staf_dokter_assigned > 0: set ke dokter tsb
        - id_staf_dokter_assigned == -1 atau None: clear (NULL = bebas)
        """
        kunjungan = self.kunjungan_repo.get_by_id(id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan dengan ID {id_kunjungan} tidak ditemukan.",
            )

        status_sekarang = kunjungan.status_antrian or ""
        if status_sekarang in ("COMPLETED", "BATAL"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Status '{status_sekarang}' adalah status final — "
                    "tidak bisa ubah dokter dituju lagi."
                ),
            )

        old_dokter = kunjungan.id_staf_dokter_assigned
        new_dokter = (
            id_staf_dokter_assigned
            if (id_staf_dokter_assigned is not None and id_staf_dokter_assigned > 0)
            else None
        )

        try:
            kunjungan.id_staf_dokter_assigned = new_dokter
            self.db.flush()

            self.audit.log_update(
                id_staf=actor_id_staf,
                tabel="kunjungan",
                id_target=id_kunjungan,
                data_lama={"id_staf_dokter_assigned": old_dokter},
                data_baru={"id_staf_dokter_assigned": new_dokter},
                request=request,
            )

            self.db.commit()
            self.db.refresh(kunjungan)
            return {
                "status": "success",
                "message": (
                    f"Dokter dituju di-clear (bebas)" if new_dokter is None
                    else f"Dokter dituju di-update ke ID {new_dokter}"
                ),
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal ubah dokter dituju: {e!s}",
            )

    def ubah_status(
        self,
        id_kunjungan: int,
        status_baru: StatusAntrianEnum,
        allow_batal: bool = True,
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
        id_staf_dokter_assigned: Optional[int] = None,  # FO-ASSIGN-DOKTER #329
        catatan_batal: Optional[str] = None,  # CA: FO catatan untuk audit trail saat BATAL
    ) -> dict:
        """
        Ubah status antrian dengan validasi transisi state machine.

        - Status terminal (COMPLETED, BATAL) tidak bisa berubah lagi.
        - Transisi harus ada di _VALID_TRANSITIONS.
        - allow_batal=False untuk role yang tidak boleh BATAL (perawat/kasir).
        """
        kunjungan = self.kunjungan_repo.get_by_id(id_kunjungan)
        if kunjungan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kunjungan dengan ID {id_kunjungan} tidak ditemukan.",
            )

        status_sekarang = kunjungan.status_antrian or "ANTRI_KONSULTASI"
        status_baru_str = status_baru.value if hasattr(status_baru, "value") else str(status_baru)

        if status_sekarang in ("COMPLETED", "BATAL"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Status '{status_sekarang}' adalah status final — "
                    f"tidak bisa diubah lagi."
                ),
            )

        if status_baru_str == "BATAL" and not allow_batal:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Role Anda tidak diizinkan membatalkan kunjungan. "
                    "Hubungi FO/Admin/Owner."
                ),
            )

        allowed = _VALID_TRANSITIONS.get(status_sekarang, set())
        if status_baru_str not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Transisi status tidak valid: '{status_sekarang}' → "
                    f"'{status_baru_str}'. Yang diizinkan: "
                    f"{sorted(allowed) or 'tidak ada (terminal)'}."
                ),
            )

        try:
            self.kunjungan_repo.update_status(kunjungan, status_baru_str)

            # FO-ASSIGN-DOKTER #329: kalau caller pass dokter assignment, update juga.
            # Berlaku ke semua transition (FO bisa assign / reassign / clear).
            if id_staf_dokter_assigned is not None:
                kunjungan.id_staf_dokter_assigned = (
                    id_staf_dokter_assigned if id_staf_dokter_assigned > 0 else None
                )
                self.db.flush()

            # CA: kalau status_baru BATAL dan ada catatan, log dengan custom aksi BATAL_ANTRIAN
            # supaya audit reviewer mudah filter & lihat alasan.
            if status_baru_str == "BATAL" and catatan_batal:
                self.audit.log(
                    aksi="BATAL_ANTRIAN",
                    id_staf=actor_id_staf or 0,
                    tabel_target="kunjungan",
                    id_target=id_kunjungan,
                    data_lama={"status_antrian": status_sekarang},
                    data_baru={"status_antrian": "BATAL", "catatan_fo": catatan_batal},
                    keterangan=f"Batal antrian: {catatan_batal}",
                    request=request,
                )
            else:
                self.audit.log_update(
                    id_staf=actor_id_staf,
                    tabel="kunjungan",
                    id_target=id_kunjungan,
                    data_lama={"status_antrian": status_sekarang},
                    data_baru={"status_antrian": status_baru_str},
                    request=request,
                )

            self.db.commit()
            self.db.refresh(kunjungan)

            return {
                "status": "success",
                "message": (
                    f"Kunjungan #{id_kunjungan} status berhasil diubah dari "
                    f"'{status_sekarang}' ke '{status_baru_str}'."
                ),
                "data": {
                    "id_kunjungan": kunjungan.id_kunjungan,
                    "status_antrian": kunjungan.status_antrian,
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal ubah status kunjungan: {e!s}",
            )


    # =========================================================================
    # BELI PRODUK ONLY - FO flow tanpa konsultasi (pasien beli krim/vitamin)
    # =========================================================================
    def beli_produk_lengkap(
        self,
        id_pasien: int,
        produk_list: list[dict],
        id_staf_fo: int,
        keluhan_utama: str = "",
        request: Optional[Request] = None,
    ) -> dict:
        """
        FO flow untuk pasien yang langsung beli produk tanpa konsultasi.

        Atomic: validasi pasien, generate antrian, create kunjungan dengan
        status=ANTRI_BAYAR, create N kunjungan_resep (status=PENDING).
        Kasir tinggal proses tagihan dengan produk yang sudah ditambahkan.

        produk_list format: [{"id_produk": int, "qty": float, "aturan_pakai": str}, ...]
        """
        from app.db.models import KunjunganResep
        from app.repositories.pemeriksaan_repo import PemeriksaanRepository

        # Validasi pasien
        pasien = self.pasien_repo.get_by_id(id_pasien)
        if pasien is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pasien dengan ID {id_pasien} tidak ditemukan.",
            )

        # Duplicate guard - sama dengan kunjungan_lama
        existing = self.kunjungan_repo.get_active_kunjungan_today(id_pasien)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Pasien '{pasien.nama}' sudah ada di antrian hari ini "
                    f"(no.antrean #{existing.nomor_antrean}, status "
                    f"{existing.status_antrian}). Tidak boleh daftar 2x."
                ),
            )

        # Validasi produk_list tidak kosong
        valid_produk = [p for p in produk_list if p.get("id_produk")]
        if not valid_produk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Minimal 1 produk wajib dipilih untuk Beli Produk.",
            )

        # Validasi semua produk exists
        pemeriksaan_repo = PemeriksaanRepository(self.db)
        for p in valid_produk:
            if not pemeriksaan_repo.get_produk_exists(int(p["id_produk"])):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"master_produk dengan id {p['id_produk']} tidak ditemukan.",
                )

        try:
            from datetime import datetime
            nomor_antrean = self.kunjungan_repo.get_nomor_antrian_berikutnya()
            kunjungan = Kunjungan(
                id_pasien=id_pasien,
                status_antrian="ANTRI_BAYAR",
                keluhan_utama=(keluhan_utama or "").strip() or None,
                id_staf_fo=id_staf_fo,
                nomor_antrean=nomor_antrean,
                sumber_pendaftaran="WALK_IN",
                tgl_kunjungan=datetime.now(),  # explicit untuk konsistensi timezone
            )
            self.kunjungan_repo.create(kunjungan)
            id_kunjungan_baru = kunjungan.id_kunjungan

            # Insert resep rows (id_staf_input WAJIB — NOT NULL di DB)
            for p in valid_produk:
                resep = KunjunganResep(
                    id_kunjungan=id_kunjungan_baru,
                    id_produk=int(p["id_produk"]),
                    qty=float(p.get("qty") or 1.0),
                    aturan_pakai=(p.get("aturan_pakai") or "").strip() or None,
                    id_staf_input=id_staf_fo,
                )
                pemeriksaan_repo.add_resep(resep)

            # Audit
            self.audit.log_create(
                id_staf=id_staf_fo,
                tabel="kunjungan",
                id_target=id_kunjungan_baru,
                data_baru={
                    "id_pasien": id_pasien,
                    "nomor_antrean": nomor_antrean,
                    "status_antrian": "ANTRI_BAYAR",
                    "sumber_pendaftaran": "WALK_IN",
                    "flow": "BELI_PRODUK_ONLY",
                    "jumlah_resep": len(valid_produk),
                },
                request=request,
            )

            self.db.commit()
            self.db.refresh(kunjungan)

            return {
                "status": "success",
                "message": (
                    f"Pasien '{pasien.nama}' didaftarkan beli produk. "
                    f"No.antrean #{nomor_antrean}, langsung ke kasir."
                ),
                "data": {
                    "id_kunjungan": kunjungan.id_kunjungan,
                    "nomor_antrean": nomor_antrean,
                    "id_pasien": id_pasien,
                    "jumlah_produk": len(valid_produk),
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Gagal proses kunjungan: {e!s}",
            )

    def update_status(self, id_kunjungan: int, payload, id_staf_actor: int, request=None):
        """Placeholder — actual implementation di kunjungan_service flows."""
        raise HTTPException(status_code=501, detail="update_status not directly used in v1")


__all__ = ["KunjunganService"]
