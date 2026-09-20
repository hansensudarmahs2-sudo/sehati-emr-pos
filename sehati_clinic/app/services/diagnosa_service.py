"""Diagnosa service (modul #24–#27).

Menangani:
- Kamus diagnosa (ref_diagnosa): ICD-10 WHO + estetik internal JD-xxx.
- Paket default per diagnosa (diagnosa_paket_item) → auto-fill tindakan/resep.
- Diagnosa per kunjungan (kunjungan_diagnosa): multi, primer/sekunder, snapshot.

Akses DB langsung via session (select 2.0) — konsisten & ringan untuk modul baru.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select, func

from app.db.models.diagnosa import RefDiagnosa, DiagnosaPaketItem, KunjunganDiagnosa
from app.db.models.treatment import MasterTreatment
from app.db.models.produk import MasterProduk
from app.db.models._enums import SistemDiagnosaEnum, TipeItemPaketEnum


class DiagnosaService:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- SEARCH
    def search(self, q: str, limit: int = 15) -> list[RefDiagnosa]:
        """Autocomplete: cocokkan kode atau nama (aktif saja)."""
        q = (q or "").strip()
        if not q:
            return []
        like = f"%{q}%"
        stmt = (
            select(RefDiagnosa)
            .where(
                RefDiagnosa.is_active == True,  # noqa: E712
                or_(RefDiagnosa.kode.like(like), RefDiagnosa.nama.like(like),
                    RefDiagnosa.nama_en.like(like)),
            )
            .order_by(RefDiagnosa.sistem.asc(), RefDiagnosa.kode.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------ MASTER CRUD
    def list_ref(self, keyword: Optional[str] = None, sistem: Optional[str] = None,
                 only_active: bool = False, limit: int = 500) -> list[RefDiagnosa]:
        stmt = select(RefDiagnosa)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(RefDiagnosa.kode.like(like), RefDiagnosa.nama.like(like),
                                  RefDiagnosa.nama_en.like(like)))
        if sistem in ("ICD10", "ESTETIK"):
            stmt = stmt.where(RefDiagnosa.sistem == SistemDiagnosaEnum(sistem))
        if only_active:
            stmt = stmt.where(RefDiagnosa.is_active == True)  # noqa: E712
        stmt = stmt.order_by(RefDiagnosa.sistem.asc(), RefDiagnosa.kode.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_ref(self, id_diagnosa: int) -> RefDiagnosa:
        obj = self.db.get(RefDiagnosa, id_diagnosa)
        if obj is None:
            raise HTTPException(status_code=404, detail="Diagnosa tidak ditemukan.")
        return obj

    def create_ref(self, *, sistem: str, kode: str, nama: str, nama_en: Optional[str],
                   kategori: Optional[str], default_kontrol_hari: int) -> RefDiagnosa:
        sistem = (sistem or "").strip().upper()
        if sistem not in ("ICD10", "ESTETIK"):
            raise HTTPException(400, "Sistem harus ICD10 atau ESTETIK.")
        kode = (kode or "").strip()
        nama = (nama or "").strip()
        if not kode or not nama:
            raise HTTPException(400, "Kode dan nama wajib diisi.")
        dup = self.db.scalar(
            select(RefDiagnosa).where(
                RefDiagnosa.sistem == SistemDiagnosaEnum(sistem),
                RefDiagnosa.kode == kode,
            )
        )
        if dup is not None:
            raise HTTPException(409, f"Kode '{kode}' sudah ada untuk sistem {sistem}.")
        obj = RefDiagnosa(
            sistem=SistemDiagnosaEnum(sistem), kode=kode, nama=nama,
            nama_en=(nama_en or None), kategori=(kategori or None),
            default_kontrol_hari=int(default_kontrol_hari or (14 if sistem == "ESTETIK" else 7)),
            is_active=True,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update_ref(self, id_diagnosa: int, *, nama: str, nama_en: Optional[str],
                   kategori: Optional[str], default_kontrol_hari: int) -> RefDiagnosa:
        obj = self.get_ref(id_diagnosa)
        nama = (nama or "").strip()
        if not nama:
            raise HTTPException(400, "Nama wajib diisi.")
        obj.nama = nama
        obj.nama_en = (nama_en or None)
        obj.kategori = (kategori or None)
        obj.default_kontrol_hari = int(default_kontrol_hari or obj.default_kontrol_hari)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def toggle_active(self, id_diagnosa: int) -> RefDiagnosa:
        obj = self.get_ref(id_diagnosa)
        obj.is_active = not bool(obj.is_active)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    # --------------------------------------------------------------- PAKET
    def list_paket(self, id_diagnosa: int) -> list[dict]:
        """Paket item + nama treatment/produk (untuk editor & autofill)."""
        items = list(self.db.execute(
            select(DiagnosaPaketItem)
            .where(DiagnosaPaketItem.id_diagnosa == id_diagnosa)
            .order_by(DiagnosaPaketItem.urutan.asc(), DiagnosaPaketItem.id_paket_item.asc())
        ).scalars().all())
        out = []
        for it in items:
            nama = "-"
            kode = None
            if it.tipe_item == TipeItemPaketEnum.TREATMENT and it.id_treatment:
                t = self.db.get(MasterTreatment, it.id_treatment)
                nama = t.nama_treatment if t else "(treatment terhapus)"
            elif it.tipe_item == TipeItemPaketEnum.PRODUK and it.id_produk:
                p = self.db.get(MasterProduk, it.id_produk)
                nama = p.nama_produk if p else "(produk terhapus)"
                kode = p.kode_produk if p else None
            out.append({
                "id_paket_item": it.id_paket_item,
                "tipe_item": it.tipe_item.value,
                "id_treatment": it.id_treatment,
                "id_produk": it.id_produk,
                "kode_produk": kode,
                "nama": nama,
                "qty_default": float(it.qty_default or 1),
                "aturan_pakai_default": it.aturan_pakai_default or "",
                "urutan": it.urutan,
            })
        return out

    def add_paket_item(self, id_diagnosa: int, *, tipe_item: str,
                       id_treatment: Optional[int] = None, id_produk: Optional[int] = None,
                       qty_default: float = 1, aturan_pakai_default: Optional[str] = None) -> None:
        self.get_ref(id_diagnosa)  # validasi ada
        tipe = (tipe_item or "").strip().upper()
        if tipe not in ("TREATMENT", "PRODUK"):
            raise HTTPException(400, "Tipe item harus TREATMENT atau PRODUK.")
        if tipe == "TREATMENT":
            if not id_treatment:
                raise HTTPException(400, "Pilih treatment.")
            id_produk = None
        else:
            if not id_produk:
                raise HTTPException(400, "Pilih produk.")
            id_treatment = None
        max_urut = self.db.scalar(
            select(func.coalesce(func.max(DiagnosaPaketItem.urutan), 0))
            .where(DiagnosaPaketItem.id_diagnosa == id_diagnosa)
        ) or 0
        self.db.add(DiagnosaPaketItem(
            id_diagnosa=id_diagnosa,
            tipe_item=TipeItemPaketEnum(tipe),
            id_treatment=id_treatment,
            id_produk=id_produk,
            qty_default=Decimal(str(qty_default or 1)),
            aturan_pakai_default=(aturan_pakai_default or None),
            urutan=int(max_urut) + 1,
        ))
        self.db.commit()

    def delete_paket_item(self, id_paket_item: int) -> None:
        obj = self.db.get(DiagnosaPaketItem, id_paket_item)
        if obj is not None:
            self.db.delete(obj)
            self.db.commit()

    # --------------------------------------------------- KUNJUNGAN DIAGNOSA
    def get_kunjungan_diagnosa(self, id_kunjungan: int) -> list[dict]:
        rows = list(self.db.execute(
            select(KunjunganDiagnosa)
            .where(KunjunganDiagnosa.id_kunjungan == id_kunjungan)
            .order_by(KunjunganDiagnosa.is_primer.desc(), KunjunganDiagnosa.urutan.asc())
        ).scalars().all())
        return [{
            "id_kunjungan_diagnosa": r.id_kunjungan_diagnosa,
            "id_diagnosa": r.id_diagnosa,
            "sistem": r.sistem_snapshot,
            "kode": r.kode_snapshot,
            "nama": r.nama_snapshot,
            "is_primer": bool(r.is_primer),
        } for r in rows]

    def save_kunjungan_diagnosa(self, id_kunjungan: int, entries: list[dict]) -> Optional[int]:
        """Replace semua diagnosa kunjungan. Return default_kontrol_hari dari diagnosa primer (atau None)."""
        # hapus lama
        for old in self.db.execute(
            select(KunjunganDiagnosa).where(KunjunganDiagnosa.id_kunjungan == id_kunjungan)
        ).scalars().all():
            self.db.delete(old)

        primary_kontrol: Optional[int] = None
        has_primer = any(e.get("is_primer") for e in entries)
        for i, e in enumerate(entries):
            nama = (e.get("nama") or "").strip()
            if not nama:
                continue
            is_primer = bool(e.get("is_primer")) or (not has_primer and i == 0)
            id_diag = e.get("id_diagnosa")
            self.db.add(KunjunganDiagnosa(
                id_kunjungan=id_kunjungan,
                id_diagnosa=id_diag,
                sistem_snapshot=(e.get("sistem") or None),
                kode_snapshot=(e.get("kode") or None),
                nama_snapshot=nama[:255],
                is_primer=is_primer,
                urutan=i,
            ))
            if is_primer and primary_kontrol is None and id_diag:
                ref = self.db.get(RefDiagnosa, id_diag)
                if ref is not None:
                    primary_kontrol = int(ref.default_kontrol_hari or 0) or None
        self.db.flush()
        return primary_kontrol
