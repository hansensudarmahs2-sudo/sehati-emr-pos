"""
KomisiReportService — laporan & dashboard komisi (baca dari komisi_ledger). K-L3.

Ref KOMISI_MODULE_DESIGN.md §5 + DEC-087.
- Filter: rentang tanggal (harian/mingguan/bulanan/rentang = ditentukan pemanggil) + opsional 1 staf.
- Dashboard: total komisi TINDAKAN, PRODUK, KESELURUHAN.
- Rincian per baris: tanggal, pasien, item, harga jual, komisi.
- Hanya status AKTIF (VOID dikecualikan). Agregasi pakai Decimal (A9), convert float di boundary.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from app.db.models import KomisiLedger, MasterStaf, Pasien, StafRoleEnum


class KomisiReportService:
    def __init__(self, db):
        self.db = db

    def laporan(self, tgl_dari: date, tgl_sampai: date, id_staf: Optional[int] = None) -> dict:
        conds = [
            KomisiLedger.status == "AKTIF",
            KomisiLedger.tanggal >= tgl_dari,
            KomisiLedger.tanggal <= tgl_sampai,
        ]
        if id_staf is not None:
            conds.append(KomisiLedger.id_staf == id_staf)

        stmt = (
            select(KomisiLedger, Pasien.no_rm, Pasien.nama, MasterStaf.nama_staf)
            .outerjoin(Pasien, Pasien.id_pasien == KomisiLedger.id_pasien)
            .outerjoin(MasterStaf, MasterStaf.id_staf == KomisiLedger.id_staf)
            .where(*conds)
            .order_by(KomisiLedger.tanggal, KomisiLedger.id_komisi)
        )
        rows = self.db.execute(stmt).all()

        total_tindakan = Decimal("0")
        total_produk = Decimal("0")
        per_staf: dict = {}
        rincian = []

        for k, no_rm, nama_pasien, nama_staf in rows:
            nom = Decimal(str(k.komisi_nominal or 0))
            if k.sumber == "TINDAKAN":
                total_tindakan += nom
            elif k.sumber == "PRODUK":
                total_produk += nom

            ps = per_staf.setdefault(k.id_staf, {
                "id_staf": k.id_staf, "nama_staf": nama_staf or "-",
                "role": k.role_snapshot, "tindakan": Decimal("0"), "produk": Decimal("0"),
            })
            if k.sumber == "TINDAKAN":
                ps["tindakan"] += nom
            else:
                ps["produk"] += nom

            rincian.append({
                "tanggal": k.tanggal,
                "id_pasien": k.id_pasien,
                "no_rm": no_rm or "-",
                "nama_pasien": nama_pasien or "-",
                "sumber": k.sumber,
                "nama_item": k.nama_item or "-",
                "harga_jual": float(k.harga_jual or 0),
                "role": k.role_snapshot,
                "nama_staf": nama_staf or "-",
                "komisi": float(nom),
            })

        per_staf_list = [
            {
                "id_staf": v["id_staf"], "nama_staf": v["nama_staf"], "role": v["role"],
                "tindakan": float(v["tindakan"]), "produk": float(v["produk"]),
                "total": float(v["tindakan"] + v["produk"]),
            }
            for v in per_staf.values()
        ]
        per_staf_list.sort(key=lambda x: -x["total"])

        return {
            "periode": {"dari": tgl_dari, "sampai": tgl_sampai},
            "filter_staf": id_staf,
            "ringkasan": {
                "total_tindakan": float(total_tindakan),
                "total_produk": float(total_produk),
                "total_semua": float(total_tindakan + total_produk),
                "jumlah_baris": len(rincian),
            },
            "per_staf": per_staf_list,
            "rincian": rincian,
        }

    def list_staf_komisi(self) -> list:
        """Daftar staf penerima komisi (Dokter & Perawat) untuk dropdown filter."""
        rows = self.db.execute(
            select(MasterStaf)
            .where(MasterStaf.role.in_([StafRoleEnum.DOKTER, StafRoleEnum.PERAWAT]))
            .order_by(MasterStaf.nama_staf)
        ).scalars().all()
        return [
            {"id_staf": s.id_staf, "nama_staf": s.nama_staf,
             "role": s.role.value if hasattr(s.role, "value") else str(s.role)}
            for s in rows
        ]


__all__ = ["KomisiReportService"]
