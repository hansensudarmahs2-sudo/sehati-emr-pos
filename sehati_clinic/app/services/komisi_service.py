"""
KomisiService — tulis & void baris komisi (ledger) saat transaksi dibayar/di-void.

Ref KOMISI_MODULE_DESIGN.md + DEC-087. K-L2.

Prinsip:
- SNAPSHOT saat bayar: nilai komisi dikunci ke `komisi_ledger` (ubah rate master nanti tak mengubahnya).
- Atribusi (pelaksana):
  * TINDAKAN → komisi_dokter ke `kunjungan_tindakan.id_dokter_pelaksana`,
               komisi_perawat ke `kunjungan_tindakan.id_perawat_pelaksana`.
               Rate 0 / pelaksana kosong → tak ada baris untuk role itu.
  * PRODUK & RACIKAN → komisi_dokter ke dokter yang di-assign kunjungan (peresep);
               kalau kunjungan TIDAK di-assign, FALLBACK ke dokter penulis SOAP pertama
               (2026-09-21, task #52). Aman karena `input_medis_lengkap` memblokir dokter
               lain menulis SOAP milik kunjungan yang sudah di-assign — jadi saat assigned
               terisi, orangnya sama; saat NULL, penulis SOAP adalah satu-satunya atribusi
               yang bermakna. SEBELUMNYA: assigned NULL → komisi produk & racikan TIDAK
               ditulis sama sekali, tanpa peringatan di mana pun (kebocoran senyap).
               "Beli tanpa konsul" (tanpa kunjungan/SOAP sama sekali) → tetap tanpa komisi.
- Basis komisi = harga MASTER (treatment.harga / produk.harga_jual) → NOMINAL flat dibayar konsisten,
  PERSEN = % harga master (independen diskon/kuota). (Bisa disesuaikan bila dr. Hansen mau basis lain.)
- Basis tanggal = tanggal bayar. VOID transaksi → baris komisi status VOID.
"""

from datetime import date
from typing import Optional

from fastapi import Request
from sqlalchemy import select

from app.db.models import (
    KomisiLedger,
    KunjunganTindakan,
    MasterProduk,
    MasterTreatment,
)
from app.db.models._enums import StatusTindakanEnum
from app.services.audit_service import AuditService
from app.services.master_produk_service import hitung_komisi_produk
from app.services.master_treatment_service import hitung_komisi_treatment


class KomisiService:
    def __init__(self, db):
        self.db = db
        self.audit = AuditService(db)

    # ---------------------------------------------------------------------
    # Tulis komisi saat bayar (dipanggil dari kasir_service.proses_bayar,
    # SEBELUM commit — ikut 1 transaksi atomik). FLUSH, caller commit.
    # ---------------------------------------------------------------------
    def catat_komisi_transaksi(
        self,
        *,
        id_transaksi: int,
        id_kunjungan: int,
        id_pasien: Optional[int],
        id_dokter_assigned: Optional[int],
        rincian_produk,
        rincian_racikan=None,
        tanggal: Optional[date] = None,
        request: Optional[Request] = None,
    ) -> int:
        """Tulis komisi untuk SEMUA tindakan SELESAI di kunjungan (termasuk gratis series/kuota)
        + produk yang dibayar. Opsi A (DEC-088). Return jumlah baris ditulis."""
        tgl = tanggal or date.today()
        n = 0

        # Task #52 — dokter efektif untuk komisi PRODUK & RACIKAN.
        # Kalau FO tidak menetapkan dokter di pendaftaran (default dropdown = "Bebas"),
        # komisi dulu hilang sama sekali. Sekarang jatuh ke dokter penulis SOAP PERTAMA
        # (yang benar-benar mengerjakan konsul); revisi SOAP berikutnya tidak memindahkan
        # komisi ke orang lain.
        id_dokter_komisi = id_dokter_assigned
        if not id_dokter_komisi:
            from app.db.models import PemeriksaanKlinis as _PK
            id_dokter_komisi = self.db.execute(
                select(_PK.id_staf_dokter)
                .where(
                    _PK.id_kunjungan == id_kunjungan,
                    _PK.id_staf_dokter.is_not(None),
                )
                .order_by(_PK.id_pemeriksaan.asc())
                .limit(1)
            ).scalar_one_or_none()

        # ---- TINDAKAN (semua SELESAI di kunjungan, bukan hanya yang ditagih) ----
        tindakan_rows = self.db.execute(
            select(KunjunganTindakan).where(
                KunjunganTindakan.id_kunjungan == id_kunjungan,
                KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI,
            )
        ).scalars().all()
        for kt in tindakan_rows:
            # Anti-dobel: skip kalau tindakan ini sudah punya baris komisi AKTIF (split/reopen).
            already = self.db.execute(
                select(KomisiLedger.id_komisi).where(
                    KomisiLedger.sumber == "TINDAKAN",
                    KomisiLedger.id_ref == kt.id_kunjungan_tindakan,
                    KomisiLedger.status == "AKTIF",
                ).limit(1)
            ).first()
            if already:
                continue
            treatment = self.db.get(MasterTreatment, kt.id_treatment)
            if treatment is None:
                continue
            calc = hitung_komisi_treatment(self.db, treatment)  # basis harga master
            harga = float(treatment.harga or 0)
            nama = treatment.nama_treatment

            kom_dok = float(calc.get("komisi_dokter", 0) or 0)
            if kt.id_dokter_pelaksana and kom_dok > 0:
                self._add_row(
                    id_transaksi=id_transaksi, id_kunjungan=id_kunjungan, id_pasien=id_pasien,
                    tanggal=tgl, id_staf=kt.id_dokter_pelaksana, role="DOKTER", sumber="TINDAKAN",
                    id_ref=kt.id_kunjungan_tindakan, nama_item=nama, harga_jual=harga,
                    komisi_tipe=treatment.komisi_dokter_tipe,
                    komisi_value=float(treatment.komisi_dokter_value or 0),
                    komisi_nominal=kom_dok,
                )
                n += 1

            kom_per = float(calc.get("komisi_perawat", 0) or 0)
            if kt.id_perawat_pelaksana and kom_per > 0:
                self._add_row(
                    id_transaksi=id_transaksi, id_kunjungan=id_kunjungan, id_pasien=id_pasien,
                    tanggal=tgl, id_staf=kt.id_perawat_pelaksana, role="PERAWAT", sumber="TINDAKAN",
                    id_ref=kt.id_kunjungan_tindakan, nama_item=nama, harga_jual=harga,
                    komisi_tipe=treatment.komisi_perawat_tipe,
                    komisi_value=float(treatment.komisi_perawat_value or 0),
                    komisi_nominal=kom_per,
                )
                n += 1

        # ---- PRODUK ---- (komisi_dokter → dokter peresep; lihat id_dokter_komisi di atas)
        if id_dokter_komisi:
            for rp in (rincian_produk or []):
                produk = self.db.get(MasterProduk, rp.id_produk)
                if produk is None:
                    continue
                calc = hitung_komisi_produk(produk)  # per unit
                kom_unit = float(calc.get("komisi_dokter", 0) or 0)
                qty = float(getattr(rp, "qty", 0) or 0)
                kom_total = kom_unit * qty
                if kom_total > 0:
                    self._add_row(
                        id_transaksi=id_transaksi, id_kunjungan=id_kunjungan, id_pasien=id_pasien,
                        tanggal=tgl, id_staf=id_dokter_komisi, role="DOKTER", sumber="PRODUK",
                        id_ref=getattr(rp, "id_resep", None) or rp.id_produk,
                        nama_item=getattr(rp, "nama_produk", None) or produk.nama_produk,
                        harga_jual=float(getattr(rp, "harga_satuan", 0) or 0),
                        komisi_tipe=produk.komisi_dokter_tipe,
                        komisi_value=float(produk.komisi_dokter_value or 0),
                        komisi_nominal=kom_total,
                    )
                    n += 1

        # ---- RACIKAN ---- komisi dihitung dari BAHAN saja; ongkos racik (jasa) TIDAK
        # masuk dasar komisi (keputusan dr. Hansen 2026-09-21). Tiap bahan memakai
        # aturan komisi produknya sendiri, persis seperti resep biasa.
        if id_dokter_komisi:
            for rr in (rincian_racikan or []):
                for bahan in (getattr(rr, "bahan", None) or []):
                    if not getattr(bahan, "id_produk", None):
                        continue  # bahan non-inventori — tidak ada master produknya
                    produk = self.db.get(MasterProduk, bahan.id_produk)
                    if produk is None:
                        continue
                    calc = hitung_komisi_produk(produk)  # per unit
                    kom_unit = float(calc.get("komisi_dokter", 0) or 0)
                    dipakai = float(getattr(bahan, "dipakai", 0) or 0)
                    kom_total = kom_unit * dipakai
                    if kom_total > 0:
                        self._add_row(
                            id_transaksi=id_transaksi, id_kunjungan=id_kunjungan,
                            id_pasien=id_pasien, tanggal=tgl, id_staf=id_dokter_komisi,
                            role="DOKTER", sumber="RACIKAN",
                            id_ref=rr.id_kunjungan_racikan,
                            nama_item=f"{rr.nama} — {bahan.nama}",
                            harga_jual=float(produk.harga_jual or 0),
                            komisi_tipe=produk.komisi_dokter_tipe,
                            komisi_value=float(produk.komisi_dokter_value or 0),
                            komisi_nominal=kom_total,
                        )
                        n += 1

        if n:
            self.db.flush()
        return n

    def _add_row(self, **kw) -> None:
        # call-site pakai role= untuk keterbacaan; kolom model = role_snapshot.
        if "role" in kw:
            kw["role_snapshot"] = kw.pop("role")
        self.db.add(KomisiLedger(status="AKTIF", **kw))

    # ---------------------------------------------------------------------
    # VOID: saat transaksi di-void → baris komisi terkait jadi VOID. FLUSH.
    # ---------------------------------------------------------------------
    def void_komisi_transaksi(self, id_transaksi: int, actor_id_staf: Optional[int] = None,
                              request: Optional[Request] = None) -> int:
        rows = self.db.execute(
            select(KomisiLedger).where(
                KomisiLedger.id_transaksi == id_transaksi,
                KomisiLedger.status == "AKTIF",
            )
        ).scalars().all()
        for r in rows:
            r.status = "VOID"
        if rows:
            self.db.flush()
            self.audit.log(
                aksi="VOID_KOMISI", id_staf=actor_id_staf, tabel_target="komisi_ledger",
                id_target=id_transaksi, keterangan=f"{len(rows)} baris komisi di-VOID", request=request,
            )
        return len(rows)


__all__ = ["KomisiService"]
