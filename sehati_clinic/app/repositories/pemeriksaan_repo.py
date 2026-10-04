"""
PemeriksaanRepository — CRUD untuk:
- pemeriksaan_klinis (SOAP)
- kunjungan_tindakan (single tindakan hari ini)
- pasien_rencana_treatment (series plan)
- kunjungan_resep (resep produk)

Plus helper untuk dashboard dokter (riwayat SOAP, produk dibeli, treatment selesai).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Kunjungan,
    KunjunganResep,
    KunjunganTindakan,
    MasterProduk,
    MasterStaf,
    MasterTreatment,
    PasienRencanaTreatment,
    PemeriksaanKlinis,
    StatusTindakanEnum,
)


class PemeriksaanRepository:
    """CRUD untuk SOAP + tindakan baru + resep + queries dashboard dokter."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # CREATE — SOAP
    # =========================================================================
    def create_soap(self, soap: PemeriksaanKlinis) -> PemeriksaanKlinis:
        self.db.add(soap)
        self.db.flush()
        return soap

    # =========================================================================
    # CREATE — Tindakan single (di-eksekusi hari ini oleh perawat)
    # =========================================================================
    def add_tindakan_hari_ini(self, tindakan: KunjunganTindakan) -> KunjunganTindakan:
        self.db.add(tindakan)
        self.db.flush()
        return tindakan

    # =========================================================================
    # CREATE — Rencana series (N rows ke pasien_rencana_treatment)
    # =========================================================================
    def add_rencana_series(self, rencana: PasienRencanaTreatment) -> PasienRencanaTreatment:
        self.db.add(rencana)
        self.db.flush()
        return rencana

    # =========================================================================
    # CREATE — Resep produk
    # =========================================================================
    def add_resep(self, resep: KunjunganResep) -> KunjunganResep:
        self.db.add(resep)
        self.db.flush()
        return resep

    # =========================================================================
    # READ — Lookup nama master untuk snapshot
    # =========================================================================
    def get_nama_treatment(self, id_treatment: int) -> Optional[str]:
        """Get nama_treatment dari master_treatment (untuk snapshot di rencana)."""
        stmt = select(MasterTreatment.nama_treatment).where(
            MasterTreatment.id_treatment == id_treatment
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_produk_exists(self, id_produk: int) -> bool:
        """Cek master_produk exists (validasi sebelum INSERT resep)."""
        stmt = select(MasterProduk.id_produk).where(MasterProduk.id_produk == id_produk)
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def get_treatment_exists(self, id_treatment: int) -> bool:
        stmt = select(MasterTreatment.id_treatment).where(
            MasterTreatment.id_treatment == id_treatment
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

    # =========================================================================
    # READ — Dashboard dokter (4 cardbox)
    # =========================================================================
    def get_tindakan_by_kunjungan(
        self,
        id_kunjungan: int,
    ) -> list[tuple[KunjunganTindakan, MasterTreatment]]:
        """
        List existing tindakan (single) untuk 1 kunjungan + JOIN nama treatment.
        Dipakai untuk display "Tindakan sebelumnya" di Ubah Konsul mode.
        """
        stmt = (
            select(KunjunganTindakan, MasterTreatment)
            .join(MasterTreatment, KunjunganTindakan.id_treatment == MasterTreatment.id_treatment)
            .where(KunjunganTindakan.id_kunjungan == id_kunjungan)
            .order_by(KunjunganTindakan.id_kunjungan_tindakan.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def get_rencana_series_by_kunjungan(
        self,
        id_kunjungan: int,
    ) -> list[PasienRencanaTreatment]:
        """List existing series tindakan yang dibuat dari kunjungan ini."""
        stmt = (
            select(PasienRencanaTreatment)
            .where(PasienRencanaTreatment.id_kunjungan_pembuat == id_kunjungan)
            .order_by(PasienRencanaTreatment.urutan_sesi.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_resep_by_kunjungan(
        self,
        id_kunjungan: int,
    ) -> list[tuple[KunjunganResep, MasterProduk]]:
        """
        List existing resep untuk 1 kunjungan + JOIN nama produk.
        Dipakai untuk display "Resep sebelumnya" di Ubah Konsul mode.
        """
        stmt = (
            select(KunjunganResep, MasterProduk)
            .join(MasterProduk, KunjunganResep.id_produk == MasterProduk.id_produk)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .order_by(KunjunganResep.id_resep.asc())
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def get_latest_soap_by_kunjungan(
        self,
        id_kunjungan: int,
    ) -> Optional[PemeriksaanKlinis]:
        """
        Return SOAP terbaru untuk 1 kunjungan (DESC by created_at).

        Dipakai untuk pre-fill form di "Ubah Konsul" mode.
        Service `input_medis_lengkap` selalu INSERT (audit trail-friendly),
        jadi bisa ada multi-row per kunjungan — kita ambil yang terbaru.
        """
        # Draf apoteker dikecualikan: pemanggil fungsi ini (form SOAP dokter, ruang
        # tindakan, cetak) semuanya mengharapkan catatan yang SUDAH sah. Draf diambil
        # lewat `get_draf_apotek` yang terpisah.
        stmt = (
            select(PemeriksaanKlinis)
            .where(PemeriksaanKlinis.id_kunjungan == id_kunjungan,
                   PemeriksaanKlinis.status_soap == "FINAL")
            .order_by(PemeriksaanKlinis.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_draf_apotek(self, id_kunjungan: int) -> Optional[PemeriksaanKlinis]:
        """Draf SOAP yang disusun apoteker dan BELUM disetujui dokter."""
        return self.db.execute(
            select(PemeriksaanKlinis)
            .where(PemeriksaanKlinis.id_kunjungan == id_kunjungan,
                   PemeriksaanKlinis.status_soap == "DRAFT_APOTEK")
            .order_by(PemeriksaanKlinis.id_pemeriksaan.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_draf_apotek(self, id_staf_dokter: Optional[int] = None) -> list:
        """Antrian draf yang menunggu persetujuan. `id_staf_dokter` = dokter yang dituju
        (diambil dari `kunjungan.id_staf_dokter_assigned`)."""
        from app.db.models import Kunjungan, Pasien

        stmt = (
            select(PemeriksaanKlinis, Kunjungan, Pasien)
            .join(Kunjungan, Kunjungan.id_kunjungan == PemeriksaanKlinis.id_kunjungan)
            .join(Pasien, Pasien.id_pasien == PemeriksaanKlinis.id_pasien)
            .where(PemeriksaanKlinis.status_soap == "DRAFT_APOTEK")
            .order_by(PemeriksaanKlinis.id_pemeriksaan.asc())
        )
        if id_staf_dokter is not None:
            stmt = stmt.where(Kunjungan.id_staf_dokter_assigned == id_staf_dokter)
        return list(self.db.execute(stmt).all())

    def get_riwayat_soap(
        self,
        id_pasien: int,
        limit: int = 10,
    ) -> list[tuple[PemeriksaanKlinis, Optional[MasterStaf]]]:
        """
        Riwayat SOAP pasien, sorted DESC by created_at, LEFT JOIN ke dokter.

        DEDUPE per tanggal: kalau ada multiple SOAP di hari yang sama
        (mis. dokter Ubah Konsul beberapa kali), hanya ambil yang TERBARU.
        Database tetap simpan semua (audit trail), tapi view hanya tampil 1 per hari.
        Implementasi: ambil lebih banyak (3x limit) di SQL, dedup di Python by date.
        """
        # Ambil over-fetch karena perlu dedup di Python
        over_fetch = limit * 3 if limit < 50 else limit
        stmt = (
            select(PemeriksaanKlinis, MasterStaf)
            .outerjoin(MasterStaf, PemeriksaanKlinis.id_staf_dokter == MasterStaf.id_staf)
            .where(PemeriksaanKlinis.id_pasien == id_pasien,
                   # Riwayat pasien hanya memuat catatan yang SUDAH disetujui dokter.
                   PemeriksaanKlinis.status_soap == "FINAL")
            .order_by(PemeriksaanKlinis.created_at.desc())
            .limit(over_fetch)
        )
        rows = self.db.execute(stmt).all()

        # Dedup by date (ambil yang pertama per date karena sudah ORDER BY DESC)
        seen_dates = set()
        deduped: list[tuple] = []
        for row in rows:
            soap = row[0]
            if soap.created_at is None:
                # Edge case — kalau ada SOAP tanpa created_at, tetap masukkan
                deduped.append((row[0], row[1]))
            else:
                date_key = soap.created_at.date()
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    deduped.append((row[0], row[1]))
            if len(deduped) >= limit:
                break
        return deduped

    def get_produk_dibeli(
        self,
        id_pasien: int,
        limit: int = 10,
    ) -> list[tuple[KunjunganResep, MasterProduk, Kunjungan]]:
        """Riwayat produk yang sudah DIBAYAR dari kunjungan_resep."""
        stmt = (
            select(KunjunganResep, MasterProduk, Kunjungan)
            .join(Kunjungan, KunjunganResep.id_kunjungan == Kunjungan.id_kunjungan)
            .join(MasterProduk, KunjunganResep.id_produk == MasterProduk.id_produk)
            .where(Kunjungan.id_pasien == id_pasien)
            .where(KunjunganResep.status_item == "DIBAYAR")
            .order_by(Kunjungan.tgl_kunjungan.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def get_treatment_selesai(
        self,
        id_pasien: int,
        limit: int = 10,
    ) -> list[tuple[KunjunganTindakan, MasterTreatment, Kunjungan]]:
        """Treatment SELESAI untuk pasien — cardbox kanan-bawah dashboard dokter.

        ⚠ DIPERBAIKI 2026-10-04. Versi sebelumnya ditulis terhadap model yang tidak
        pernah ada dan **tidak mungkin pernah berhasil** — empat kesalahan sekaligus:

        | Ditulis | Kenyataannya |
        |---|---|
        | `KunjunganTindakan.id_pasien` | tidak ada; pasien hanya terjangkau lewat `kunjungan` |
        | `KunjunganTindakan.status` | namanya `status_tindakan` |
        | `KunjunganTindakan.tgl_selesai` | namanya `waktu_selesai` |
        | `== "COMPLETED"` | enumnya PENDING/PROSES/**SELESAI** — "COMPLETED" tak pernah cocok |

        Akibatnya `GET /api/v1/dokter/pasien/{id}/summary` SELALU membalas 500
        (`AttributeError`). Tidak ada yang melaporkannya karena UI klinik tidak memakai
        endpoint itu — nol rujukan di 127 template.

        Mengembalikan TIGA nilai, bukan dua: pemanggilnya
        (`pemeriksaan_service.get_summary_pasien`) membongkar `tindakan, tr, kj` dan
        memakai `kj.tgl_kunjungan` sebagai tanggal. Tanggal diambil dari KUNJUNGAN,
        bukan dari `waktu_selesai`, supaya sebaris dengan `get_produk_dibeli` di atas —
        dua cardbox bersebelahan tidak boleh memakai sumber tanggal yang berbeda.
        """
        stmt = (
            select(KunjunganTindakan, MasterTreatment, Kunjungan)
            .join(Kunjungan, KunjunganTindakan.id_kunjungan == Kunjungan.id_kunjungan)
            .join(MasterTreatment, KunjunganTindakan.id_treatment == MasterTreatment.id_treatment)
            .where(Kunjungan.id_pasien == id_pasien)
            .where(KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI)
            .order_by(Kunjungan.tgl_kunjungan.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], row[1], row[2]) for row in rows]


__all__ = ["PemeriksaanRepository"]
