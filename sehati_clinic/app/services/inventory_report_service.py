"""
InventoryReportService — laporan inventory berbasis lot (P-L8):
1. ed_report      : bucket ED (<1bln/<3bln/<6bln/<1thn) + daftar lot mendekati ED.
2. slow_moving    : rasio stok saat ini vs pengeluaran/bulan (window 3 bulan), urut paling lambat.
3. price_trend    : harga order vs harga terima per produk lintas waktu (naik/turun).

Ref INVENTORY_LOT_ED_MODULE_DESIGN.md §10.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from app.db.models import (
    StokLot, MasterProduk, InventoryStok, PemesananReceive, PemesananItem, Pemesanan,
)


class InventoryReportService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ ED
    def ed_report(self, today: Optional[date] = None) -> dict:
        today = today or date.today()
        horizon = today + timedelta(days=366)
        rows = self.db.execute(
            select(StokLot).where(
                StokLot.status == "AKTIF",
                StokLot.qty_sisa > 0,
                StokLot.tgl_ed.isnot(None),
                StokLot.tgl_ed <= horizon,
            ).order_by(StokLot.tgl_ed.asc())
        ).scalars().all()

        # name resolver
        pid = {l.id_produk for l in rows if l.id_produk}
        bid = {l.id_bahan for l in rows if l.id_bahan}
        pmap = {}
        bmap = {}
        if pid:
            for p in self.db.execute(select(MasterProduk).where(MasterProduk.id_produk.in_(pid))).scalars():
                pmap[p.id_produk] = p.nama_produk
        if bid:
            for b in self.db.execute(select(InventoryStok).where(InventoryStok.id_bahan.in_(bid))).scalars():
                bmap[b.id_bahan] = b.nama_bahan

        buckets = {"lt1": 0, "lt3": 0, "lt6": 0, "lt12": 0}
        items = []
        for l in rows:
            days = (l.tgl_ed - today).days
            if days < 30:
                bkt = "lt1"
            elif days < 90:
                bkt = "lt3"
            elif days < 180:
                bkt = "lt6"
            else:
                bkt = "lt12"
            buckets[bkt] += 1
            items.append({
                "nama": (pmap.get(l.id_produk) if l.tipe_item == "PRODUK" else bmap.get(l.id_bahan)) or "(?)",
                "tipe_item": l.tipe_item, "lokasi": l.lokasi,
                "batch_no": l.batch_no or "-", "tgl_ed": l.tgl_ed,
                "days": days, "qty_sisa": float(l.qty_sisa or 0),
                "bucket": bkt,
            })
        return {"buckets": buckets, "lots": items, "total": len(items), "today": today}

    # ------------------------------------------------------ SLOW-MOVING (produk)
    def slow_moving(self, today: Optional[date] = None) -> list:
        today = today or date.today()
        sejak = datetime.now() - timedelta(days=90)
        from app.repositories.apotek_repo import ApotekRepository
        qty_map = ApotekRepository(self.db).get_qty_terjual_per_produk(sejak)  # {id_produk: qty 90h}

        produks = self.db.execute(
            select(MasterProduk).where(MasterProduk.is_active == True).order_by(MasterProduk.nama_produk)
        ).scalars().all()
        out = []
        for p in produks:
            stok = float(p.stok_terkini or 0)
            terjual_90 = float(qty_map.get(p.id_produk, 0) or 0)
            per_bulan = terjual_90 / 3.0
            # bulan stok tersisa = stok / pemakaian per bulan (makin besar = makin lambat)
            bulan_tersisa = (stok / per_bulan) if per_bulan > 0 else (None if stok > 0 else 0)
            out.append({
                "id_produk": p.id_produk, "nama_produk": p.nama_produk,
                "kode_produk": p.kode_produk, "satuan": p.satuan,
                "stok_terkini": stok, "terjual_90": terjual_90,
                "per_bulan": round(per_bulan, 2),
                "bulan_tersisa": (round(bulan_tersisa, 1) if bulan_tersisa is not None else None),
                "harga_jual": float(p.harga_jual or 0),
            })
        # urut: paling lambat dulu — stok ada tapi tak terjual (per_bulan 0) di atas, lalu bulan_tersisa desc
        def _key(r):
            if r["per_bulan"] == 0 and r["stok_terkini"] > 0:
                return (0, -r["stok_terkini"])   # mati total, prioritas
            return (1, -(r["bulan_tersisa"] or 0))
        out.sort(key=_key)
        return out

    # ------------------------------------------------------- PRICE TREND
    def price_trend(self) -> list:
        rows = self.db.execute(
            select(PemesananReceive, PemesananItem, Pemesanan)
            .join(PemesananItem, PemesananItem.id_item == PemesananReceive.id_pemesanan_item)
            .join(Pemesanan, Pemesanan.id_pemesanan == PemesananReceive.id_pemesanan)
            .where(PemesananReceive.harga_terima.isnot(None))
            .order_by(PemesananReceive.tgl_terima.asc())
        ).all()
        by_item: dict = {}
        for rcv, item, po in rows:
            key = item.id_produk if item.tipe_item == "PRODUK" else ("B", item.id_bahan)
            rec = by_item.setdefault(key, {
                "nama": item.nama_snapshot, "tipe_item": item.tipe_item, "riwayat": [],
            })
            rec["riwayat"].append({
                "tgl": rcv.tgl_terima, "nomor_po": po.nomor_po,
                "harga_order": float(item.harga_satuan) if item.harga_satuan is not None else None,
                "harga_terima": float(rcv.harga_terima),
            })
        out = []
        for rec in by_item.values():
            r = rec["riwayat"]
            first = r[0]["harga_terima"]
            last = r[-1]["harga_terima"]
            delta = last - first
            out.append({
                "nama": rec["nama"], "tipe_item": rec["tipe_item"],
                "harga_pertama": first, "harga_terakhir": last, "delta": delta,
                "arah": ("naik" if delta > 0 else ("turun" if delta < 0 else "tetap")),
                "n": len(r), "riwayat": r,
            })
        out.sort(key=lambda x: -abs(x["delta"]))
        return out


__all__ = ["InventoryReportService"]
