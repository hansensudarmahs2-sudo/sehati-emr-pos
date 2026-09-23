"""
PasienRepository — CRUD untuk pasien + alergi + penyakit kronis.

Plus helper untuk generate nomor RM dengan format YYMMDD-NNN (counter harian).
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    MasterProduk,
    Pasien,
    PasienAlergi,
    PasienPenyakitKronis,
    PasienRencanaTreatment,
    TransaksiDetailProduk,
    TransaksiKasir,
)


class PasienRepository:
    """CRUD untuk tabel pasien (+ relasi alergi & penyakit kronis)."""

    def __init__(self, db: Session):
        self.db = db

    # ----- Pasien core -----
    def get_by_id(self, id_pasien: int, with_relations: bool = False) -> Optional[Pasien]:
        if with_relations:
            stmt = (
                select(Pasien)
                .options(selectinload(Pasien.alergi), selectinload(Pasien.penyakit_kronis))
                .where(Pasien.id_pasien == id_pasien)
            )
            return self.db.execute(stmt).scalar_one_or_none()
        return self.db.get(Pasien, id_pasien)

    def search(self, keyword: str, limit: int = 50) -> list[Pasien]:
        """
        Cari pasien by nama, no_rm, nomor telepon, atau alamat (case-insensitive).

        Note: alamat bisa return banyak hasil kalau keyword umum (mis. "Jakarta").
        Limit default 50 cukup untuk Phase 1.
        """
        term = f"%{keyword}%"
        stmt = (
            select(Pasien)
            # Task #18: pasien NONAKTIF (duplikat yang sudah dibereskan) tidak boleh
            # muncul di pencarian — kalau muncul, petugas bisa memilihnya lagi dan
            # duplikatnya hidup kembali. Datanya tetap utuh & bisa dibuka lewat URL
            # langsung dari halaman audit.
            .where(Pasien.is_active.is_(True))
            .where(
                or_(
                    Pasien.nama.ilike(term),
                    Pasien.no_rm.ilike(term),
                    Pasien.nomor_telepon.ilike(term),
                    Pasien.alamat.ilike(term),
                )
            )
            .order_by(Pasien.nama.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ----- Deteksi duplikat (identitas) -----
    def find_by_nik(self, nik: str):
        """Cari pasien dgn NIK/KTP sama persis (non-kosong). None kalau tak ada."""
        nik = (nik or "").strip()
        if not nik:
            return None
        # Hanya pasien AKTIF yang memblokir pendaftaran. Duplikat yang sudah
        # dinonaktifkan NIK-nya sudah dilepas, jadi tidak akan ikut tersaring —
        # filter ini pagar kedua kalau ada baris lama yang NIK-nya belum dilepas.
        return (
            self.db.query(Pasien)
            .filter(Pasien.nomor_ktp == nik, Pasien.is_active.is_(True))
            .first()
        )

    def find_by_dob_gender(self, tgl_lahir, jenis_kelamin) -> list[Pasien]:
        """Kandidat utk cek nama-sama: pasien dgn tgl_lahir + jenis_kelamin sama.
        Filter nama (normalisasi) dilakukan di service. [] kalau tgl_lahir None."""
        if tgl_lahir is None:
            return []
        return (
            self.db.query(Pasien)
            .filter(
                Pasien.tgl_lahir == tgl_lahir,
                Pasien.jenis_kelamin == jenis_kelamin,
                Pasien.is_active.is_(True),  # jangan peringatkan soal duplikat yang sudah dibereskan
            )
            .all()
        )

    def create(self, pasien: Pasien) -> Pasien:
        self.db.add(pasien)
        self.db.flush()  # assign id_pasien
        return pasien

    def update(self, pasien: Pasien, data: dict) -> Pasien:
        for key, value in data.items():
            setattr(pasien, key, value)
        self.db.flush()
        return pasien

    # ----- No RM generator dengan counter harian -----
    def generate_next_no_rm(self, today: Optional[date] = None) -> str:
        """
        Generate no_rm berikutnya dengan format YYMMDD-NNN.

        Pakai SELECT ... FOR UPDATE untuk lock supaya tidak kolisi
        kalau 2 FO daftar pasien bersamaan.

        Example: 260517-001, 260517-002, dst.
        """
        if today is None:
            today = date.today()

        date_part = today.strftime("%y%m%d")  # "260517"

        # MK-L3: prefix cabang dari config klinik (master_klinik_config.rm_prefix);
        # fallback ke env rm_clinic_prefix (DEC-071a). Berlaku pendaftaran baru.
        from app.db.models import MasterKlinikConfig
        cfg = self.db.get(MasterKlinikConfig, 1)
        clinic = (
            (cfg.rm_prefix if cfg and cfg.rm_prefix else get_settings().rm_clinic_prefix) or ""
        ).strip()
        rm_prefix = f"{clinic}-{date_part}" if clinic else date_part

        # Lock row pasien dengan prefix sama hari ini supaya tidak ada
        # concurrent insert yang bisa race.
        stmt = text("""
            SELECT no_rm FROM pasien
            WHERE no_rm LIKE :prefix
            ORDER BY no_rm DESC
            LIMIT 1
            FOR UPDATE
        """)
        result = self.db.execute(stmt, {"prefix": f"{rm_prefix}-%"}).first()

        if result and result[0]:
            # Parse counter dari segmen TERAKHIR no_rm:
            # "260517-007" -> 7, "A-260517-007" -> 7 (sama-sama benar).
            last_no_rm = result[0]
            try:
                last_counter = int(last_no_rm.split("-")[-1])
                next_counter = last_counter + 1
            except (IndexError, ValueError):
                next_counter = 1
        else:
            next_counter = 1

        return f"{rm_prefix}-{next_counter:03d}"  # "A-260517-001"

    # ----- Alergi -----
    def add_alergi(self, alergi: PasienAlergi) -> PasienAlergi:
        self.db.add(alergi)
        self.db.flush()
        return alergi

    def get_alergi_aktif(self, id_pasien: int) -> list[PasienAlergi]:
        stmt = (
            select(PasienAlergi)
            .where(
                PasienAlergi.id_pasien == id_pasien,
                PasienAlergi.is_active.is_(True),
            )
            .order_by(PasienAlergi.id_alergi.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def soft_delete_alergi(self, id_alergi: int) -> bool:
        """Soft delete — set is_active=False. Return True kalau row terupdate."""
        alergi = self.db.get(PasienAlergi, id_alergi)
        if alergi is None:
            return False
        alergi.is_active = False
        self.db.flush()
        return True

    # ----- Penyakit kronis -----
    def add_penyakit_kronis(self, penyakit: PasienPenyakitKronis) -> PasienPenyakitKronis:
        self.db.add(penyakit)
        self.db.flush()
        return penyakit

    def get_penyakit_kronis_aktif(self, id_pasien: int) -> list[PasienPenyakitKronis]:
        stmt = (
            select(PasienPenyakitKronis)
            .where(
                PasienPenyakitKronis.id_pasien == id_pasien,
                PasienPenyakitKronis.is_active.is_(True),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def soft_delete_penyakit_kronis(self, id_penyakit: int) -> bool:
        """TODO-NEW-1 #29B - Soft delete penyakit kronis."""
        penyakit = self.db.get(PasienPenyakitKronis, id_penyakit)
        if penyakit is None:
            return False
        penyakit.is_active = False
        self.db.flush()
        return True

    # =========================================================================
    # RIWAYAT — untuk endpoint GET /pasien/{id}/riwayat
    # =========================================================================
    def get_ringkasan_kunjungan(
        self,
        id_pasien: int,
        limit: int = 20,
    ) -> list[Kunjungan]:
        """
        List kunjungan pasien, sorted DESC by tgl_kunjungan.

        `limit` default 20 — secukupnya untuk panel FO. Bisa di-extend
        kalau Bapak butuh lihat semua history.
        """
        stmt = (
            select(Kunjungan)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(Kunjungan.tgl_kunjungan.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_riwayat_treatment(self, id_pasien: int) -> list[PasienRencanaTreatment]:
        """List semua series treatment pasien, urut by urutan_sesi ASC."""
        stmt = (
            select(PasienRencanaTreatment)
            .where(PasienRencanaTreatment.id_pasien == id_pasien)
            .order_by(
                PasienRencanaTreatment.created_at.desc(),
                PasienRencanaTreatment.urutan_sesi.asc(),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_riwayat_tindakan_diresepkan(
        self,
        id_pasien: int,
        limit: int = 20,
    ) -> list[tuple]:
        """
        Tindakan SINGLE yang diresepkan dokter via SOAP (dari kunjungan_tindakan).
        JOIN master_treatment untuk nama+harga, JOIN kunjungan untuk tgl.
        Mirip pattern get_riwayat_produk_resep. Sorted DESC by tgl_kunjungan.
        """
        from app.db.models import KunjunganTindakan, MasterTreatment
        stmt = (
            select(KunjunganTindakan, MasterTreatment, Kunjungan)
            .join(Kunjungan, KunjunganTindakan.id_kunjungan == Kunjungan.id_kunjungan)
            .join(MasterTreatment, KunjunganTindakan.id_treatment == MasterTreatment.id_treatment)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(Kunjungan.tgl_kunjungan.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def get_riwayat_produk_resep(
        self,
        id_pasien: int,
    ) -> list[tuple[KunjunganResep, MasterProduk, Kunjungan]]:
        """
        Produk yang DIRESEPKAN — JOIN kunjungan_resep + master_produk + kunjungan.

        Return list of (KunjunganResep, MasterProduk, Kunjungan) tuples,
        sorted DESC by tgl_kunjungan.
        """
        stmt = (
            select(KunjunganResep, MasterProduk, Kunjungan)
            .join(Kunjungan, KunjunganResep.id_kunjungan == Kunjungan.id_kunjungan)
            .join(MasterProduk, KunjunganResep.id_produk == MasterProduk.id_produk)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(Kunjungan.tgl_kunjungan.desc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def get_riwayat_produk_terbayar(
        self,
        id_pasien: int,
    ) -> list[tuple]:
        """Produk yang sudah DIBAYAR via transaksi kasir. JOIN ke detail + produk + kunjungan."""
        stmt = (
            select(TransaksiDetailProduk, MasterProduk, TransaksiKasir)
            .join(TransaksiKasir, TransaksiDetailProduk.id_transaksi == TransaksiKasir.id_transaksi)
            .join(MasterProduk, TransaksiDetailProduk.id_produk == MasterProduk.id_produk)
            .join(Kunjungan, TransaksiKasir.id_kunjungan == Kunjungan.id_kunjungan)
            .where(Kunjungan.id_pasien == id_pasien)
            .order_by(TransaksiKasir.waktu_bayar.desc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]


__all__ = ["PasienRepository"]
