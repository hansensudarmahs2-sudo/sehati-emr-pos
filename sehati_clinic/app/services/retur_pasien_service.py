"""
ReturPasienService — retur obat/produk yang SUDAH diserahkan ke pasien.

Rancangan & keputusan dr. Hansen 2026-10-05: Project_Memory/DESAIN_RETUR_DARI_PASIEN.md.
Tahap 2: REFUND. Tahap 3: TUKAR. Tahap 4: ALERGI.

ALERGI (keputusan dr. Hansen 2026-10-05, §10b/§12): retur beralasan ALERGI membuat
KUNJUNGAN BARU `jenis_kunjungan='RETUR_PASIEN'` (langsung COMPLETED, tanpa tagihan,
ditujukan ke dokter peresep asal) berisi draf SOAP status DRAFT_APOTEK — pola tebus resep
online. ⚠ BUKAN di kunjungan asal: `get_riwayat_soap` menampilkan SATU SOAP FINAL per
kunjungan, jadi draf yang disetujui di sana akan MENGGANTIKAN SOAP konsultasi asli di riwayat.
Saat dokter menyetujui, `catat_alergi_dari_retur` menambah `pasien_alergi` (alergen dicek
dokter, keparahan WAJIB dipilih dokter) dalam commit yang sama dengan SOAP-nya.
Kunjungan retur TIDAK dihitung di rekap/laporan kunjungan (keputusan 11.2) — lihat
`JENIS_KUNJUNGAN_BUKAN_KLINIS` dan pembacanya.

TUKAR (keputusan dr. Hansen 2026-10-05, §10a): obat asal X diretur, produk pengganti Y
diserahkan SEKARANG. Uang hanya selisih:
  Y >= X -> kredit tukar = X, pasien membayar Y - X (masuk laci, metode biasa);
  Y <  X -> kredit tukar = Y, sisa X - Y HANGUS (tidak dikembalikan, tidak jadi saldo),
            ditandai `nilai_hangus` untuk Finance — tetap pendapatan penjualan X.
Pembukuan: refund X ber-metode 'TUKAR' sebesar kredit + transaksi BARU jenis 'TUKAR'
(kunjungan yang sama) berisi Y, dibayar 'TUKAR' sebesar kredit (+ selisih). Metode 'TUKAR'
masuk dan keluar dengan nilai sama -> saling meniadakan; tutup kasir hanya menghitung
METODE_KANONIK, jadi laci hanya melihat selisih yang benar-benar dibayar.
Komisi: TIDAK disentuh — komisi X tetap, Y tidak berkomisi ("tukar tidak pernah menambah
komisi"). Y diserahkan dengan potong FEFO + jejak lot persis seperti apotek; fungsi serah
apotek tidak dipakai karena ia menolak kunjungan COMPLETED dan meng-commit sendiri.

Aturan yang dijaga di SERVER (layar bukan pagar):
- hanya item `DISERAHKAN`, paling lambat 7 hari sejak `waktu_serah` (keputusan 2);
- qty ≤ qty diserahkan − qty yang sudah pernah diretur; racikan selalu utuh;
- PIN Admin/Superadmin/Owner (≠ pemroses) kalau retur SEBAGIAN (keputusan 1) atau
  transaksi asal hari lampau (aturan refund T32) — memakai pagar PIN yang sama dengan T32;
- baris item dikunci (`with_for_update`): dua retur bersamaan atas item yang sama tidak
  boleh sama-sama lolos cek sisa qty (Temuan 15/19/20).

Uang — jalur T32, bukan jalur baru: baris `transaksi_refund` (jenis `RETUR`) dibukukan di
HARI RETUR lewat `_refund_bukuan`; header transaksi asal TIDAK disentuh; void transaksi asal
sesudahnya ditolak oleh pagar T32 (`_pagari_void_sudah_refund`).

Komisi (keputusan 3): retur PENUH → baris komisi item di-VOID (`void_komisi_item`). Retur
SEBAGIAN → baris koreksi NEGATIF proporsional, bertanggal hari retur. Baris asli tidak
diubah (jejak tetap utuh); kalau sisanya diretur kemudian, `void_komisi_item` mem-VOID
baris asli BERSAMA koreksinya → totalnya tepat nol.

Stok: `stok_kembali=True` → qty kembali ke LOT ASAL lewat jejak `kunjungan_lot_terpakai`
(ED terjaga), dicatat per lot di `retur_pasien_lot` dan di `inventory_history` jenis
RETUR_PASIEN. ⚠ `reversed_at` jejak SENGAJA tidak disentuh: void menandai seluruh baris
jejak, tapi retur bisa sebagian — jumlah yang sudah kembali dihitung dari
`retur_pasien_lot`. Racikan tidak pernah kembali stok. `stok_kembali=False` → tidak ada
gerak stok (barang sudah keluar); `nilai_kerugian` = harga terima lot (fallback HPP).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AlasanReturPasienEnum, JenisMutasiEnum, JenisReturPasienEnum, KomisiLedger,
    KunjunganLotTerpakai, KunjunganResep, MasterProduk, ReturPasien, ReturPasienLot,
    StokLot, TransaksiKasir, TransaksiRefund,
)
from app.db.models.racikan import KunjunganRacikan
from app.repositories.inventory_repo import InventoryRepository
from app.services.audit_service import AuditService
from app.services.kasir_service import KasirService
from app.services.komisi_service import KomisiService

BATAS_HARI = 7          # keputusan dr. Hansen 2026-10-05
# Definisi tunggal ada di _jenis_kunjungan (dipakai juga dashboard/rekap/ekspor).
from app.services._jenis_kunjungan import JENIS_KUNJUNGAN_BUKAN_KLINIS, JENIS_RETUR  # noqa: E402
_EPS = Decimal("0.0001")


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


class ReturPasienService:
    def __init__(self, db: Session):
        self.db = db
        self.kasir = KasirService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ util
    def _sudah_diretur(self, *, id_resep=None, id_kunjungan_racikan=None) -> Decimal:
        kol = (ReturPasien.id_resep == id_resep) if id_resep is not None \
            else (ReturPasien.id_kunjungan_racikan == id_kunjungan_racikan)
        return _d(self.db.execute(
            select(func.coalesce(func.sum(ReturPasien.qty), 0)).where(kol)).scalar())

    def _lot_tersedia_untuk_kembali(self, item: KunjunganResep) -> list:
        """[(jejak, qty_masih_bisa_kembali)] — jejak lot item ini dikurangi yang sudah
        dikembalikan lewat retur sebelumnya."""
        jejak = self.db.execute(
            select(KunjunganLotTerpakai).where(
                KunjunganLotTerpakai.id_resep == item.id_resep,
                KunjunganLotTerpakai.id_produk == item.id_produk,
                KunjunganLotTerpakai.reversed_at.is_(None),
            ).order_by(KunjunganLotTerpakai.id_terpakai)
        ).scalars().all()
        out = []
        for j in jejak:
            sudah = _d(self.db.execute(
                select(func.coalesce(func.sum(ReturPasienLot.qty), 0))
                .join(ReturPasien, ReturPasien.id_retur == ReturPasienLot.id_retur)
                .where(ReturPasien.id_resep == item.id_resep, ReturPasienLot.id_lot == j.id_lot)
            ).scalar())
            sisa = _d(j.qty) - sudah
            if sisa > _EPS:
                out.append((j, sisa))
        return out

    def _koreksi_komisi_sebagian(self, *, id_transaksi, sumber, id_ref, fraksi: Decimal,
                                 actor_id_staf, request) -> int:
        rows = self.db.execute(select(KomisiLedger).where(
            KomisiLedger.id_transaksi == id_transaksi, KomisiLedger.sumber == sumber,
            KomisiLedger.id_ref == id_ref, KomisiLedger.status == "AKTIF",
            KomisiLedger.komisi_nominal > 0,          # hanya baris asli, bukan koreksi
        )).scalars().all()
        komisi = KomisiService(self.db)
        hari_ini = datetime.now().date()
        for r in rows:
            komisi._add_row(
                id_transaksi=r.id_transaksi, id_kunjungan=r.id_kunjungan, id_pasien=r.id_pasien,
                tanggal=hari_ini, id_staf=r.id_staf, role=r.role_snapshot, sumber=r.sumber,
                id_ref=r.id_ref, nama_item=f"Retur sebagian: {r.nama_item}"[:255],
                harga_jual=r.harga_jual, komisi_tipe=r.komisi_tipe, komisi_value=r.komisi_value,
                komisi_nominal=-(_d(r.komisi_nominal) * fraksi).quantize(Decimal("0.01")),
            )
        if rows:
            self.db.flush()
            self.audit.log(aksi="KOREKSI_KOMISI_RETUR", id_staf=actor_id_staf,
                           tabel_target="komisi_ledger", id_target=id_transaksi,
                           keterangan=f"{len(rows)} baris koreksi negatif {sumber} ref={id_ref} "
                                      f"fraksi={fraksi} (retur sebagian).", request=request)
        return len(rows)

    def _harga_pengganti(self, trx, pengganti: list) -> tuple:
        """[(produk, qty, harga_satuan, subtotal, diskon_item)], total bersih Y.

        Harga jual HARI INI dengan diskon member yang sama seperti pembelian biasa
        (persen_produk tier aktif, hanya produk eligible) — pasien member tidak dirugikan
        saat menukar.
        """
        from app.db.models import Kunjungan
        id_pasien = trx.id_pasien
        if id_pasien is None and trx.id_kunjungan:
            k = self.db.get(Kunjungan, trx.id_kunjungan)
            id_pasien = k.id_pasien if k else None
        persen = Decimal("0")
        if id_pasien:
            persen = _d(self.kasir.membership.get_diskon_for_pasien(id_pasien).persen_produk)
        rows, total = [], Decimal("0")
        for p in pengganti:
            produk = self.db.get(MasterProduk, int(p["id_produk"]))
            q = _d(p.get("qty"))
            if produk is None or not produk.is_active:
                raise HTTPException(400, f"Produk pengganti #{p.get('id_produk')} tidak ada / tidak aktif.")
            if q <= 0:
                raise HTTPException(400, f"Qty pengganti {produk.nama_produk} harus > 0.")
            harga = _d(produk.harga_jual)
            sub = (harga * q).quantize(Decimal("0.01"))
            disk = ((sub * persen / 100).quantize(Decimal("0.01"))
                    if produk.eligible_member_discount else Decimal("0"))
            rows.append((produk, q, harga, sub, disk))
            total += sub - disk
        if total <= 0:
            raise HTTPException(400, "Nilai produk pengganti nol.")
        return rows, total

    def _serahkan_pengganti(self, *, trx, y_rows, nilai_pengganti, kredit, selisih,
                            metode_selisih, actor_id_staf, label) -> int:
        """Buat resep DISERAHKAN + potong stok FEFO + jejak lot + transaksi TUKAR. FLUSH.

        Urutan penting: resep pengganti ditulis SEBELUM transaksinya, karena
        `trx_dan_nilai_bersih` mencari transaksi yang dibayar sesudah resep ditulis —
        dengan begitu retur atas produk pengganti kelak menunjuk transaksi TUKAR ini.
        """
        from app.db.models import (
            StatusItemResepEnum, TransaksiDetailProduk, TransaksiKasir, TransaksiPembayaran,
        )
        from app.repositories.apotek_repo import ApotekRepository
        from app.services.apotek_service import ApotekService
        from app.services.inventory_lot_service import InventoryLotService
        repo, lot_svc, apotek = ApotekRepository(self.db), InventoryLotService(self.db), ApotekService(self.db)
        now = KasirService._now_utc7().replace(tzinfo=None)
        reseps = []
        for produk, q, harga, sub, disk in y_rows:
            r = KunjunganResep(id_kunjungan=trx.id_kunjungan, id_produk=produk.id_produk,
                               qty=float(q), status_item=StatusItemResepEnum.DISERAHKAN,
                               id_staf_input=actor_id_staf, waktu_serah=now,
                               aturan_pakai=f"Pengganti retur: {label}"[:100])
            self.db.add(r)
            reseps.append(r)
        self.db.flush()
        for r, (produk, q, harga, sub, disk) in zip(reseps, y_rows):
            p_lock = repo.get_produk_for_update(produk.id_produk)
            repo.update_stok_produk(p_lock, delta=-float(q))      # boleh minus (filosofi klinik)
            fefo = lot_svc.consume_fefo(tipe_item="PRODUK", lokasi="RETAIL", qty=float(q),
                                        id_produk=produk.id_produk)
            apotek._simpan_lot_terpakai(trx.id_kunjungan, produk.id_produk, fefo["consumed"],
                                        id_resep=r.id_resep)
        sub_total = sum((x[3] for x in y_rows), Decimal("0"))
        disk_total = sum((x[4] for x in y_rows), Decimal("0"))
        t = TransaksiKasir(
            id_kunjungan=trx.id_kunjungan, id_pasien=trx.id_pasien,
            id_staf_kasir=actor_id_staf, jenis_transaksi="TUKAR",
            rincian_tagihan=f"Pengganti retur {label}", subtotal=sub_total,
            nominal_diskon=disk_total, total_tagihan=nilai_pengganti, status_transaksi="BAYAR",
        )
        self.db.add(t)
        self.db.flush()
        for produk, q, harga, sub, disk in y_rows:
            self.db.add(TransaksiDetailProduk(id_transaksi=t.id_transaksi,
                                              id_produk=produk.id_produk, qty=float(q),
                                              harga_satuan=harga, subtotal=sub, diskon_item=disk))
        self.db.add(TransaksiPembayaran(id_transaksi=t.id_transaksi, metode_bayar="TUKAR",
                                        nominal=kredit))
        if selisih > 0:
            self.db.add(TransaksiPembayaran(id_transaksi=t.id_transaksi,
                                            metode_bayar=metode_selisih, nominal=selisih))
        self.db.flush()
        return t.id_transaksi

    # ------------------------------------------------------------------ alergi
    def _buat_kunjungan_alergi(self, *, trx, item, label, alasan_teks, actor_id_staf, now) -> int:
        """Kunjungan RETUR_PASIEN + draf SOAP untuk dokter peresep asal. FLUSH."""
        from app.db.models import Kunjungan, PemeriksaanKlinis
        asal = self.db.get(Kunjungan, item.id_kunjungan)
        id_pasien = trx.id_pasien or (asal.id_pasien if asal else None)
        dokter = asal.id_staf_dokter_assigned if asal else None
        if dokter is None and asal is not None:
            dokter = self.db.execute(
                select(PemeriksaanKlinis.id_staf_dokter)
                .where(PemeriksaanKlinis.id_kunjungan == asal.id_kunjungan,
                       PemeriksaanKlinis.status_soap == "FINAL",
                       PemeriksaanKlinis.id_staf_dokter.is_not(None))
                .order_by(PemeriksaanKlinis.id_pemeriksaan).limit(1)
            ).scalar_one_or_none()
        k = Kunjungan(id_pasien=id_pasien, tgl_kunjungan=now, status_antrian="COMPLETED",
                      jenis_kunjungan=JENIS_RETUR, id_staf_dokter_assigned=dokter,
                      keluhan_utama=f"Retur obat karena dugaan alergi: {label}"[:255])
        self.db.add(k)
        self.db.flush()
        self.db.add(PemeriksaanKlinis(
            id_kunjungan=k.id_kunjungan, id_pasien=id_pasien, id_staf_dokter=None,
            status_soap="DRAFT_APOTEK", id_staf_penyusun=actor_id_staf, waktu_konsultasi=now,
            anamnesa=(f"Pasien mengembalikan {label} (diserahkan "
                      f"{item.waktu_serah:%d/%m/%Y}, kunjungan asal #{item.id_kunjungan}) "
                      f"karena dugaan ALERGI.\nKeluhan: {alasan_teks.strip()}"),
        ))
        self.db.flush()
        return k.id_kunjungan

    def info_retur_alergi(self, id_kunjungan: int) -> Optional[dict]:
        """Prefill layar persetujuan draf, atau None kalau kunjungan ini bukan retur-alergi."""
        r = self.db.execute(select(ReturPasien).where(
            ReturPasien.id_kunjungan_retur == id_kunjungan,
            ReturPasien.alasan_kode == AlasanReturPasienEnum.ALERGI)).scalar_one_or_none()
        if r is None:
            return None
        if r.id_resep is not None:
            item = self.db.get(KunjunganResep, r.id_resep)
            produk = self.db.get(MasterProduk, item.id_produk) if item else None
            alergen = ((produk.kandungan or produk.nama_produk) if produk else "") or ""
            nama = produk.nama_produk if produk else "-"
        else:
            item = self.db.get(KunjunganRacikan, r.id_kunjungan_racikan)
            alergen = nama = (item.nama_snapshot if item else "") or ""
        return {"id_retur": r.id_retur, "nomor_retur": r.nomor_retur, "produk": nama,
                "alergen": alergen[:100], "gejala": r.alasan_teks, "sudah": r.id_alergi is not None}

    def catat_alergi_dari_retur(self, *, id_kunjungan: int, id_staf_dokter: int, alergen: str,
                                gejala: str, tingkat_keparahan: str, request=None) -> Optional[int]:
        """Dipanggil saat dokter MENYETUJUI draf retur-alergi. FLUSH — caller commit bersama
        SOAP-nya (tidak boleh ada SOAP FINAL tanpa alerginya, atau sebaliknya).

        Alergen yang sama (tanpa beda huruf besar/kecil) yang SUDAH aktif tidak ditambah dobel.
        Return id_alergi (baru atau yang sudah ada), None kalau bukan retur-alergi.
        """
        from app.db.models import PasienAlergi, TingkatKeparahanAlergiEnum
        info = self.info_retur_alergi(id_kunjungan)
        if info is None:
            return None
        r = self.db.get(ReturPasien, info["id_retur"])
        if r.id_alergi is not None:
            return r.id_alergi
        alergen = (alergen or "").strip()[:100]      # lebar kolom — pelajaran T24
        if not alergen:
            raise HTTPException(400, "Alergen wajib diisi.")
        try:
            keparahan = TingkatKeparahanAlergiEnum(tingkat_keparahan)
        except ValueError:
            raise HTTPException(400, "Tingkat keparahan alergi WAJIB dipilih dokter "
                                     "(Ringan / Sedang / Berat).")
        trx = self.db.get(TransaksiKasir, r.id_transaksi_asal)
        from app.db.models import Kunjungan
        id_pasien = trx.id_pasien or self.db.get(Kunjungan, id_kunjungan).id_pasien
        ada = self.db.execute(select(PasienAlergi).where(
            PasienAlergi.id_pasien == id_pasien, PasienAlergi.is_active.is_(True),
            func.lower(PasienAlergi.alergen) == alergen.lower())).scalars().first()
        if ada is not None:
            r.id_alergi = ada.id_alergi
            catatan = "sudah tercatat — tidak ditambah dobel"
        else:
            ada = PasienAlergi(id_pasien=id_pasien, alergen=alergen,
                               gejala=(gejala or "").strip() or None,
                               tingkat_keparahan=keparahan, is_active=True,
                               id_staf=id_staf_dokter)
            self.db.add(ada)
            self.db.flush()
            r.id_alergi = ada.id_alergi
            catatan = "ditambahkan"
        self.audit.log(aksi="ALERGI_DARI_RETUR", id_staf=id_staf_dokter,
                       tabel_target="pasien_alergi", id_target=ada.id_alergi,
                       data_baru={"id_pasien": id_pasien, "alergen": alergen,
                                  "keparahan": keparahan.value, "retur": r.nomor_retur},
                       keterangan=f"Alergi '{alergen}' {catatan} dari retur {r.nomor_retur}.",
                       request=request)
        self.db.flush()
        return ada.id_alergi

    # ------------------------------------------------------------------ layar
    def daftar_item_retur(self, id_transaksi: int) -> dict:
        """Isi layar "Retur dari pasien" untuk SATU transaksi.

        Item = resep/racikan DISERAHKAN yang transaksi asalnya (menurut
        `trx_dan_nilai_bersih` — rumus yang SAMA dengan saat retur dibuat) adalah transaksi
        INI. Memilih per kunjungan saja akan menampilkan item transaksi lain di kunjungan
        yang sama (split billing, transaksi TUKAR) — jebakan yang sama dengan nota T27.
        """
        from app.db.models import Kunjungan, Pasien, TransaksiDetailRacikan
        trx = self.db.get(TransaksiKasir, id_transaksi)
        if trx is None:
            raise HTTPException(404, f"Transaksi #{id_transaksi} tidak ditemukan.")
        k = self.db.get(Kunjungan, trx.id_kunjungan) if trx.id_kunjungan else None
        pasien = self.db.get(Pasien, trx.id_pasien or (k.id_pasien if k else None)) \
            if (trx.id_pasien or k) else None
        now = KasirService._now_utc7().replace(tzinfo=None)
        items = []
        if trx.status_transaksi == "BAYAR" and k is not None:
            reseps = self.db.execute(select(KunjunganResep).where(
                KunjunganResep.id_kunjungan == k.id_kunjungan,
                KunjunganResep.status_item == "DISERAHKAN",
            ).order_by(KunjunganResep.id_resep)).scalars().all()
            for r in reseps:
                produk = self.db.get(MasterProduk, r.id_produk)
                try:
                    t_asal, nilai = self.kasir.trx_dan_nilai_bersih(
                        item=r, id_resep=r.id_resep, id_kunjungan_racikan=None,
                        label=produk.nama_produk if produk else "-")
                except HTTPException:
                    continue
                if t_asal.id_transaksi != id_transaksi:
                    continue
                sudah = self._sudah_diretur(id_resep=r.id_resep)
                items.append(self._baris_layar(
                    jenis_item="RESEP", id_item=r.id_resep,
                    nama=produk.nama_produk if produk else "-", qty=_d(r.qty), sudah=sudah,
                    nilai=nilai, waktu_serah=r.waktu_serah, now=now, bisa_stok=True,
                    golongan=(produk.golongan if produk else None)))
            for dr in self.db.execute(select(TransaksiDetailRacikan).where(
                    TransaksiDetailRacikan.id_transaksi == id_transaksi)).scalars():
                h = self.db.get(KunjunganRacikan, dr.id_kunjungan_racikan)
                if h is None or str(h.status_item or "") != "DISERAHKAN":
                    continue
                sudah = self._sudah_diretur(id_kunjungan_racikan=h.id_kunjungan_racikan)
                items.append(self._baris_layar(
                    jenis_item="RACIKAN", id_item=h.id_kunjungan_racikan,
                    nama=f"⚗️ {h.nama_snapshot}", qty=Decimal("1"), sudah=sudah,
                    nilai=_d(dr.subtotal), waktu_serah=h.waktu_serah, now=now,
                    bisa_stok=False, golongan=None))
        produk_aktif = self.db.execute(select(MasterProduk).where(
            MasterProduk.is_active.is_(True)).order_by(MasterProduk.nama_produk)).scalars().all()
        return {
            "trx": trx, "pasien": pasien, "items": items,
            "hari_lampau": trx.waktu_bayar is not None and not KasirService._is_same_calendar_day_utc7(
                trx.waktu_bayar, KasirService._now_utc7()),
            "produk_aktif": [{"id": p.id_produk, "nama": p.nama_produk, "golongan": p.golongan,
                              "harga": float(_d(p.harga_jual))} for p in produk_aktif],
            "batas_hari": BATAS_HARI,
        }

    @staticmethod
    def _baris_layar(*, jenis_item, id_item, nama, qty, sudah, nilai, waktu_serah, now,
                     bisa_stok, golongan) -> dict:
        batas = (waktu_serah + timedelta(days=BATAS_HARI)) if waktu_serah else None
        sisa = qty - sudah
        return {
            "jenis_item": jenis_item, "id_item": id_item, "nama": nama,
            "qty": float(qty), "sudah": float(sudah), "sisa": float(sisa),
            "nilai_total": float(nilai), "waktu_serah": waktu_serah, "batas": batas,
            "lewat_batas": batas is None or now > batas, "habis": sisa <= _EPS,
            "bisa_stok": bisa_stok, "golongan": golongan,
        }

    def konteks_nota_retur(self, id_retur: int) -> dict:
        """Data nota retur. Pasien disebut nama & no_rm — nota ini untuk pasien."""
        from app.db.models import Kunjungan, MasterStaf, Pasien
        r = self.db.get(ReturPasien, id_retur)
        if r is None:
            raise HTTPException(404, f"Retur #{id_retur} tidak ditemukan.")
        trx = self.db.get(TransaksiKasir, r.id_transaksi_asal)
        k = self.db.get(Kunjungan, trx.id_kunjungan) if trx and trx.id_kunjungan else None
        pid = (trx.id_pasien if trx else None) or (k.id_pasien if k else None)
        pasien = self.db.get(Pasien, pid) if pid else None
        if r.id_resep is not None:
            item = self.db.get(KunjunganResep, r.id_resep)
            produk = self.db.get(MasterProduk, item.id_produk) if item else None
            nama = produk.nama_produk if produk else "-"
        else:
            item = self.db.get(KunjunganRacikan, r.id_kunjungan_racikan)
            nama = f"Racikan {item.nama_snapshot}" if item else "Racikan"
        refund = self.db.get(TransaksiRefund, r.id_refund) if r.id_refund else None
        pengganti = []
        if r.id_transaksi_pengganti:
            from app.db.models import TransaksiDetailProduk
            for d, n in self.db.execute(
                select(TransaksiDetailProduk, MasterProduk.nama_produk)
                .join(MasterProduk, MasterProduk.id_produk == TransaksiDetailProduk.id_produk)
                .where(TransaksiDetailProduk.id_transaksi == r.id_transaksi_pengganti)
            ).all():
                pengganti.append({"nama": n, "qty": float(d.qty),
                                  "nilai": float(_d(d.subtotal) - _d(d.diskon_item))})
        staf = self.db.get(MasterStaf, r.id_staf)
        penyetuju = self.db.get(MasterStaf, r.id_staf_otorisasi) if r.id_staf_otorisasi else None
        return {
            "r": r, "trx": trx, "pasien": pasien, "nama_item": nama,
            "metode_refund": refund.metode_refund if refund else None,
            "pengganti": pengganti, "petugas": staf.nama_staf if staf else "-",
            "penyetuju": penyetuju.nama_staf if penyetuju else None,
        }

    # ------------------------------------------------------------------ utama
    def buat_retur(
        self,
        *,
        id_resep: Optional[int] = None,
        id_kunjungan_racikan: Optional[int] = None,
        qty=None,
        jenis: str,
        alasan_kode: str,
        alasan_teks: str,
        stok_kembali: bool,
        actor_id_staf: int,
        metode_refund: str = "TUNAI",
        pengganti: Optional[list] = None,
        pratinjau: bool = False,
        setuju_hangus: bool = False,
        id_staf_otorisasi: Optional[int] = None,
        pin_otorisasi: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> dict:
        if (id_resep is None) == (id_kunjungan_racikan is None):
            raise HTTPException(400, "Pilih tepat satu: item resep ATAU racikan.")
        try:
            jenis_e = JenisReturPasienEnum(jenis)
            alasan_e = AlasanReturPasienEnum(alasan_kode)
        except ValueError:
            raise HTTPException(400, "Jenis atau alasan retur tidak dikenal.")
        is_tukar = jenis_e == JenisReturPasienEnum.TUKAR
        if is_tukar:
            pengganti = [p for p in (pengganti or []) if p]
            if not pengganti:
                raise HTTPException(400, "Retur TUKAR butuh minimal satu produk pengganti.")
            if (metode_refund or "TUNAI").upper() == "TUKAR":
                raise HTTPException(400, "Pilih metode bayar selisih yang nyata (TUNAI/QRIS/...).")
        if not (alasan_teks or "").strip():
            raise HTTPException(400, "Keluhan/alasan pasien WAJIB diisi — ini uang keluar.")

        now = KasirService._now_utc7().replace(tzinfo=None)

        # ---- 1. Item (DIKUNCI) ------------------------------------------------
        if id_resep is not None:
            item = self.db.execute(select(KunjunganResep)
                                   .where(KunjunganResep.id_resep == id_resep)
                                   .with_for_update()).scalar_one_or_none()
            if item is None:
                raise HTTPException(404, f"Resep {id_resep} tidak ditemukan.")
            st = item.status_item.value if hasattr(item.status_item, "value") else str(item.status_item or "")
            produk = self.db.get(MasterProduk, item.id_produk)
            label = f"{produk.nama_produk if produk else 'resep'} (resep #{id_resep})"
            qty_item = _d(item.qty)
            sumber_komisi, id_ref_komisi = "PRODUK", id_resep
        else:
            item = self.db.execute(select(KunjunganRacikan)
                                   .where(KunjunganRacikan.id_kunjungan_racikan == id_kunjungan_racikan)
                                   .with_for_update()).scalar_one_or_none()
            if item is None:
                raise HTTPException(404, f"Racikan {id_kunjungan_racikan} tidak ditemukan.")
            st = str(item.status_item or "")
            produk = None
            label = f"racikan {item.nama_snapshot} (#{id_kunjungan_racikan})"
            qty_item = Decimal("1")               # racikan all-or-nothing
            sumber_komisi, id_ref_komisi = "RACIKAN", id_kunjungan_racikan
            if stok_kembali:
                raise HTTPException(400, "Racikan tidak pernah kembali ke stok (dibuat khusus).")

        if st != "DISERAHKAN":
            raise HTTPException(400, f"{label} berstatus '{st}' — retur dari pasien hanya untuk "
                                     "obat yang SUDAH diserahkan. Obat yang belum diserahkan: "
                                     "pakai pembatalan di Obat Tertunda.")
        if item.waktu_serah is None:
            raise HTTPException(400, f"{label} tidak punya waktu serah — tidak bisa dinilai "
                                     "batas 7 hari.")
        if now - item.waktu_serah > timedelta(days=BATAS_HARI):
            raise HTTPException(400, f"{label} diserahkan {item.waktu_serah:%d/%m/%Y} — lewat "
                                     f"batas retur {BATAS_HARI} hari.")

        # ---- 2. Qty ------------------------------------------------------------
        sudah = self._sudah_diretur(id_resep=id_resep, id_kunjungan_racikan=id_kunjungan_racikan)
        sisa = qty_item - sudah
        if sisa <= _EPS:
            raise HTTPException(400, f"{label} sudah diretur seluruhnya.")
        if id_kunjungan_racikan is not None:
            q = sisa                               # racikan: utuh
        else:
            q = sisa if qty is None else _d(qty)
            if q <= 0:
                raise HTTPException(400, "Jumlah retur harus lebih dari 0.")
            if q > sisa + _EPS:
                raise HTTPException(400, f"Jumlah retur {q:g} melebihi sisa yang bisa diretur "
                                         f"({sisa:g} dari {qty_item:g}).")
        is_sebagian = (q < sisa - _EPS) or (sudah > _EPS)
        fraksi = (q / qty_item) if qty_item > 0 else Decimal("1")

        # ---- 3. Transaksi asal + nilai BERSIH (rumus bersama T32) ---------------
        trx, nilai = self.kasir.trx_dan_nilai_bersih(
            item=item, id_resep=id_resep, id_kunjungan_racikan=id_kunjungan_racikan,
            label=label, qty=q if id_resep is not None else None)
        if nilai <= 0:
            raise HTTPException(400, f"Nilai retur {label} nol — tidak ada yang dikembalikan.")

        # ---- 3b. TUKAR: hitung selisih SEKARANG (dr. Hansen 2026-10-05) ----------
        # "Perlu ada warning saat tukar produk yang lebih mahal atau lebih murah,
        # terutama yang lebih murah karena uang pasien akan hilang." Jadi:
        #   - `pratinjau=True` → hitung saja, TIDAK menulis apa pun, kembalikan angka
        #     untuk layar konfirmasi;
        #   - sisa hangus > 0 tanpa `setuju_hangus` → DITOLAK di server, bukan hanya di
        #     layar — centang konfirmasi tidak boleh bisa dilewati dengan form buatan.
        y_rows, nilai_pengganti = [], None
        selisih = hangus = Decimal("0")
        if is_tukar:
            y_rows, nilai_pengganti = self._harga_pengganti(trx, pengganti)
            selisih = max(Decimal("0"), nilai_pengganti - nilai)
            hangus = max(Decimal("0"), nilai - nilai_pengganti)
        if pratinjau:
            # Belum ada yang ditulis; kunci baris item lepas saat sesi permintaan ditutup.
            return {
                "status": "pratinjau", "label": label, "qty": float(q),
                "is_sebagian": is_sebagian, "nilai_retur": float(nilai),
                "pengganti": [{"id_produk": p.id_produk, "nama": p.nama_produk,
                               "qty": float(qq), "nilai": float(sub - disk)}
                              for p, qq, h, sub, disk in y_rows],
                "nilai_pengganti": float(nilai_pengganti or 0),
                "selisih_dibayar": float(selisih), "nilai_hangus": float(hangus),
                "hari_lampau": trx.waktu_bayar is not None and not KasirService._is_same_calendar_day_utc7(
                    trx.waktu_bayar, KasirService._now_utc7()),
            }
        if hangus > 0 and not setuju_hangus:
            raise HTTPException(400, (
                f"Produk pengganti lebih murah: sisa Rp {hangus:,.0f} TIDAK dikembalikan dan "
                "tidak jadi saldo. Beri tahu pasien dan centang persetujuannya di layar "
                "konfirmasi — atau pilih pengganti/qty lain.").replace(",", "."))

        # ---- 4. Otorisasi PIN ----------------------------------------------------
        hari_lampau = trx.waktu_bayar is not None and not KasirService._is_same_calendar_day_utc7(
            trx.waktu_bayar, KasirService._now_utc7())
        id_penyetuju = None
        if is_sebagian or hari_lampau:
            sebab = ("Retur SEBAGIAN" if is_sebagian else
                     f"Transaksi dibayar {trx.waktu_bayar:%d/%m/%Y} (hari lampau). Retur")
            id_penyetuju = self.kasir._otorisasi_refund_lampau(
                trx=trx, label=label, actor_id_staf=actor_id_staf,
                id_staf_otorisasi=id_staf_otorisasi, pin_otorisasi=pin_otorisasi,
                request=request, alasan_perlu=f"{sebab} {label}",
                aksi_tolak="RETUR_DITOLAK_PIN")

        try:
            # ---- 5. Stok ---------------------------------------------------------
            lot_kembali: list = []
            kerugian = Decimal("0")
            if stok_kembali:
                sisa_kembali = q
                for jejak, bisa in self._lot_tersedia_untuk_kembali(item):
                    if sisa_kembali <= _EPS:
                        break
                    ambil = min(bisa, sisa_kembali)
                    lot_kembali.append((jejak.id_lot, ambil))
                    sisa_kembali -= ambil
                if sisa_kembali > _EPS:
                    raise HTTPException(400, f"Jejak lot {label} hanya cukup untuk "
                                             f"{q - sisa_kembali:g} dari {q:g} — sisanya tidak "
                                             "pernah keluar dari lot mana pun. Pilih 'tidak "
                                             "kembali ke stok'.")
                p_lock = self.db.execute(select(MasterProduk)
                                         .where(MasterProduk.id_produk == item.id_produk)
                                         .with_for_update()).scalar_one()
                for id_lot, ambil in lot_kembali:
                    lot = self.db.execute(select(StokLot).where(StokLot.id_lot == id_lot)
                                          .with_for_update()).scalar_one()
                    lot.qty_sisa = float(_d(lot.qty_sisa) + ambil)
                    if lot.status == "HABIS":
                        lot.status = "AKTIF"
                p_lock.stok_terkini = float(_d(p_lock.stok_terkini) + q)
                InventoryRepository(self.db).add_history(
                    id_staf=actor_id_staf, jenis=JenisMutasiEnum.RETUR_PASIEN,
                    qty_perubahan=float(q), stok_akhir=float(p_lock.stok_terkini),
                    id_produk=p_lock.id_produk, tipe_item="PRODUK",
                    referensi=f"retur pasien trx #{trx.id_transaksi}",
                    keterangan=f"{label}: {q:g} kembali ke lot " +
                               ", ".join(f"#{i} +{a:g}" for i, a in lot_kembali))
            elif id_resep is not None:
                # Barang tidak kembali: nilai kerugian dari harga terima lot yang keluar.
                sisa_rugi = q
                for jejak, bisa in self._lot_tersedia_untuk_kembali(item):
                    if sisa_rugi <= _EPS:
                        break
                    ambil = min(bisa, sisa_rugi)
                    lot = self.db.get(StokLot, jejak.id_lot)
                    kerugian += ambil * _d(lot.harga_terima if lot else 0)
                    sisa_rugi -= ambil
                if sisa_rugi > _EPS and produk is not None:
                    kerugian += sisa_rugi * _d(produk.hpp_per_unit)
            kerugian = kerugian.quantize(Decimal("0.01"))

            # ---- 6. Uang -------------------------------------------------------------
            metode = (metode_refund or "TUNAI").upper()
            id_trx_pengganti = None
            if is_tukar:
                kredit = min(nilai, nilai_pengganti)       # selisih/hangus: langkah 3b
                id_trx_pengganti = self._serahkan_pengganti(
                    trx=trx, y_rows=y_rows, nilai_pengganti=nilai_pengganti, kredit=kredit,
                    selisih=selisih, metode_selisih=metode, actor_id_staf=actor_id_staf,
                    label=label)
                nilai_refund, metode_refund_baris = kredit, "TUKAR"
            else:
                nilai_refund, metode_refund_baris = nilai, metode
            # Refund dibukukan HARI INI (T32). Untuk TUKAR hanya sebesar KREDIT — sisa
            # yang hangus TIDAK dikurangkan dari omzet (tetap pendapatan penjualan X).
            refund = TransaksiRefund(
                id_transaksi=trx.id_transaksi, tgl_refund=now, nilai_refund=nilai_refund,
                metode_refund=metode_refund_baris,
                alasan=(f"Retur dari pasien ({jenis_e.value}) — {label}. {alasan_teks.strip()}"),
                id_staf_refund=actor_id_staf, id_staf_otorisasi=id_penyetuju,
                jenis_refund="RETUR", id_resep=id_resep,
                id_kunjungan_racikan=id_kunjungan_racikan,
            )
            self.db.add(refund)
            self.db.flush()

            # ---- 7. Komisi (keputusan 3) -------------------------------------------
            if is_tukar:
                n_komisi = 0      # tukar: komisi X tetap, pengganti tak berkomisi
            elif is_sebagian and q < sisa - _EPS:
                n_komisi = self._koreksi_komisi_sebagian(
                    id_transaksi=trx.id_transaksi, sumber=sumber_komisi, id_ref=id_ref_komisi,
                    fraksi=fraksi, actor_id_staf=actor_id_staf, request=request)
            else:
                # Retur penuh / sisa terakhir: VOID baris asli BESERTA koreksi sebelumnya.
                n_komisi = KomisiService(self.db).void_komisi_item(
                    id_transaksi=trx.id_transaksi, sumber=sumber_komisi, id_ref=id_ref_komisi,
                    actor_id_staf=actor_id_staf, request=request)

            # ---- 8. Baris retur + nomor dari PK -------------------------------------
            r = ReturPasien(
                nomor_retur="(sementara)", id_transaksi_asal=trx.id_transaksi,
                id_resep=id_resep, id_kunjungan_racikan=id_kunjungan_racikan,
                qty=q, is_sebagian=is_sebagian, waktu_serah_asal=item.waktu_serah,
                jenis=jenis_e, alasan_kode=alasan_e, alasan_teks=alasan_teks.strip(),
                nilai_retur=nilai, stok_kembali=bool(stok_kembali), nilai_kerugian=kerugian,
                id_refund=refund.id_refund, id_transaksi_pengganti=id_trx_pengganti,
                nilai_pengganti=nilai_pengganti, selisih_dibayar=selisih, nilai_hangus=hangus,
                id_staf=actor_id_staf, id_staf_otorisasi=id_penyetuju,
            )
            self.db.add(r)
            self.db.flush()
            r.nomor_retur = f"RPS-{now:%Y-%m}-{r.id_retur:06d}"
            if alasan_e == AlasanReturPasienEnum.ALERGI:
                r.id_kunjungan_retur = self._buat_kunjungan_alergi(
                    trx=trx, item=item, label=label, alasan_teks=alasan_teks,
                    actor_id_staf=actor_id_staf, now=now)
            for id_lot, ambil in lot_kembali:
                self.db.add(ReturPasienLot(id_retur=r.id_retur, id_lot=id_lot, qty=ambil))

            self.audit.log(
                aksi="RETUR_PASIEN", id_staf=actor_id_staf, tabel_target="retur_pasien",
                id_target=r.id_retur,
                data_baru={"nomor": r.nomor_retur, "jenis": jenis_e.value,
                           "id_transaksi_asal": trx.id_transaksi, "qty": float(q),
                           "nilai": float(nilai), "stok_kembali": bool(stok_kembali),
                           "nilai_kerugian": float(kerugian), "sebagian": is_sebagian,
                           "id_staf_otorisasi": id_penyetuju, "komisi_disentuh": n_komisi,
                           "alasan": alasan_e.value, "id_transaksi_pengganti": id_trx_pengganti,
                           "nilai_pengganti": float(nilai_pengganti or 0),
                           "selisih_dibayar": float(selisih), "nilai_hangus": float(hangus)},
                keterangan=(f"Retur {r.nomor_retur}: {label} {q:g} unit, "
                            + (f"ditukar (pengganti Rp {nilai_pengganti}, selisih dibayar "
                               f"Rp {selisih}, hangus Rp {hangus})" if is_tukar else
                               f"Rp {nilai} dikembalikan ({metode})")
                            + ", dibukukan hari ini."),
                request=request,
            )
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

        return {
            "status": "success", "nomor_retur": r.nomor_retur, "id_retur": r.id_retur,
            "jenis": jenis_e.value, "id_transaksi_pengganti": id_trx_pengganti,
            "nilai_pengganti": float(nilai_pengganti or 0), "selisih_dibayar": float(selisih),
            "nilai_hangus": float(hangus),
            "nilai": float(nilai), "qty": float(q), "sebagian": is_sebagian,
            "stok_kembali": bool(stok_kembali), "nilai_kerugian": float(kerugian),
            "message": (
                (f"Retur {r.nomor_retur}: {label} ditukar. "
                 + (f"Pasien membayar selisih Rp {selisih:,.0f} ({metode})." if selisih > 0 else
                    f"Sisa Rp {hangus:,.0f} hangus (tidak dikembalikan)." if hangus > 0 else
                    "Nilai setara, tanpa selisih."))
                if is_tukar else
                f"Retur {r.nomor_retur}: {label} {q:g} unit. Kembalikan Rp {nilai:,.0f} "
                f"({metode}) ke pasien.").replace(",", "."),
        }
