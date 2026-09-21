"""Racikan service — Formula, biaya racik, dan KALKULATOR harga.

Kalkulator di sini adalah sumber kebenaran tunggal; dipakai oleh:
- Master Formula Racikan (pratinjau harga)
- Kartu Racik di SOAP (Fase 2) → hasilnya di-snapshot ke resep

Aturan (Project_Memory/DESAIN_MODUL_RACIKAN.md, dikunci 2026-09-20):
- Mode MG (tablet)  : butir = (dosis × N) ÷ kekuatan_nilai → CEIL → ditagih penuh.
- Mode GRAM (krim)  : PRO-RATA, harga_per_gram = harga_jual ÷ isi_kemasan (tanpa CEIL).
- TOTAL = Σ biaya bahan + tarif FLAT ongkos racik per jenis.
"""
from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete, or_, select

from app.db.models.produk import MasterProduk
from app.db.models.racikan import (
    KunjunganRacikan,
    KunjunganRacikanBahan,
    MasterBiayaRacik,
    MasterRacikan,
    MasterRacikanBahan,
)

# satuan dosis yang berarti "mode gram/krim" (pro-rata)
_SATUAN_GRAM = {"gr", "g", "ml"}


def _rp(v) -> Decimal:
    """Bulatkan ke rupiah utuh."""
    return Decimal(str(v or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class RacikanService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ BIAYA RACIK
    def list_biaya_racik(self, only_active: bool = True) -> list[MasterBiayaRacik]:
        stmt = select(MasterBiayaRacik)
        if only_active:
            stmt = stmt.where(MasterBiayaRacik.is_active == True)  # noqa: E712
        return list(self.db.execute(stmt.order_by(MasterBiayaRacik.jenis_racik)).scalars().all())

    def tarif_racik(self, jenis_racik: str) -> Decimal:
        row = self.db.scalar(
            select(MasterBiayaRacik).where(MasterBiayaRacik.jenis_racik == (jenis_racik or "").upper())
        )
        return _rp(row.tarif) if row else Decimal("0")

    def update_tarif(self, id_biaya_racik: int, tarif: float) -> None:
        row = self.db.get(MasterBiayaRacik, id_biaya_racik)
        if row is None:
            raise HTTPException(404, "Jenis racik tidak ditemukan.")
        if tarif < 0:
            raise HTTPException(400, "Tarif tidak boleh negatif.")
        row.tarif = Decimal(str(tarif))
        self.db.commit()

    # ---------------------------------------------------------------- FORMULA
    def list_formula(self, keyword: Optional[str] = None, jenis: Optional[str] = None,
                     only_active: bool = False, limit: int = 500) -> list[MasterRacikan]:
        stmt = select(MasterRacikan)
        if keyword:
            stmt = stmt.where(or_(MasterRacikan.nama.like(f"%{keyword.strip()}%")))
        if jenis:
            stmt = stmt.where(MasterRacikan.jenis_racik == jenis.upper())
        if only_active:
            stmt = stmt.where(MasterRacikan.is_active == True)  # noqa: E712
        return list(self.db.execute(stmt.order_by(MasterRacikan.nama)).scalars().all())

    def get_formula(self, id_racikan: int) -> MasterRacikan:
        obj = self.db.get(MasterRacikan, id_racikan)
        if obj is None:
            raise HTTPException(404, "Formula racikan tidak ditemukan.")
        return obj

    def create_formula(self, *, nama: str, jenis_racik: str, default_jumlah_unit: int,
                       default_aturan_pakai: Optional[str] = None,
                       catatan: Optional[str] = None) -> MasterRacikan:
        nama = (nama or "").strip()
        if not nama:
            raise HTTPException(400, "Nama formula wajib diisi.")
        jenis = (jenis_racik or "").strip().upper()
        if not self.db.scalar(select(MasterBiayaRacik).where(MasterBiayaRacik.jenis_racik == jenis)):
            raise HTTPException(400, f"Jenis racik '{jenis}' tidak dikenal.")
        obj = MasterRacikan(
            nama=nama, jenis_racik=jenis,
            default_jumlah_unit=max(1, int(default_jumlah_unit or 1)),
            default_aturan_pakai=(default_aturan_pakai or None),
            catatan=(catatan or None), is_active=True,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update_formula(self, id_racikan: int, *, nama: str, jenis_racik: str,
                       default_jumlah_unit: int, default_aturan_pakai: Optional[str] = None,
                       catatan: Optional[str] = None) -> MasterRacikan:
        obj = self.get_formula(id_racikan)
        nama = (nama or "").strip()
        if not nama:
            raise HTTPException(400, "Nama formula wajib diisi.")
        jenis = (jenis_racik or "").strip().upper()
        if not self.db.scalar(select(MasterBiayaRacik).where(MasterBiayaRacik.jenis_racik == jenis)):
            raise HTTPException(400, f"Jenis racik '{jenis}' tidak dikenal.")
        obj.nama = nama
        obj.jenis_racik = jenis
        obj.default_jumlah_unit = max(1, int(default_jumlah_unit or 1))
        obj.default_aturan_pakai = (default_aturan_pakai or None)
        obj.catatan = (catatan or None)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def toggle_active(self, id_racikan: int) -> None:
        obj = self.get_formula(id_racikan)
        obj.is_active = not bool(obj.is_active)
        self.db.commit()

    # ------------------------------------------------------------------ BAHAN
    def list_bahan(self, id_racikan: int) -> list[MasterRacikanBahan]:
        return list(self.db.execute(
            select(MasterRacikanBahan)
            .where(MasterRacikanBahan.id_racikan == id_racikan)
            .order_by(MasterRacikanBahan.urutan, MasterRacikanBahan.id_racikan_bahan)
        ).scalars().all())

    def add_bahan(self, id_racikan: int, *, id_produk: int, dosis_per_unit: float,
                  satuan_dosis: str = "mg") -> None:
        self.get_formula(id_racikan)
        produk = self.db.get(MasterProduk, id_produk)
        if produk is None:
            raise HTTPException(404, "Produk bahan tidak ditemukan.")
        if not dosis_per_unit or float(dosis_per_unit) <= 0:
            raise HTTPException(400, "Dosis per unit harus lebih dari 0.")
        satuan = (satuan_dosis or "mg").strip().lower()
        # Validasi ketersediaan data dasar hitung — cegah formula yang tak bisa dihitung.
        if satuan in _SATUAN_GRAM:
            if not produk.isi_kemasan:
                raise HTTPException(
                    400, f"'{produk.nama_produk}' belum punya isi kemasan — "
                         "isi dulu di Master Produk agar harga per gram bisa dihitung.")
        elif not produk.kekuatan_nilai:
            raise HTTPException(
                400, f"'{produk.nama_produk}' belum punya kekuatan sediaan — "
                     "isi dulu di Master Produk agar jumlah butir bisa dihitung.")
        max_urut = len(self.list_bahan(id_racikan))
        self.db.add(MasterRacikanBahan(
            id_racikan=id_racikan, id_produk=id_produk,
            dosis_per_unit=Decimal(str(dosis_per_unit)),
            satuan_dosis=satuan, urutan=max_urut + 1,
        ))
        self.db.commit()

    def delete_bahan(self, id_racikan_bahan: int) -> None:
        obj = self.db.get(MasterRacikanBahan, id_racikan_bahan)
        if obj is not None:
            self.db.delete(obj)
            self.db.commit()

    # ------------------------------------------------------------- KALKULATOR
    def hitung(self, id_racikan: int, jumlah_unit: int) -> dict:
        """Hitung dari FORMULA tersimpan. Delegasi ke hitung_spec()."""
        formula = self.get_formula(id_racikan)
        n = max(1, int(jumlah_unit or formula.default_jumlah_unit or 1))
        bahan = [
            {"id_produk": b.id_produk, "dosis": b.dosis_per_unit, "satuan": b.satuan_dosis}
            for b in self.list_bahan(formula.id_racikan)
        ]
        hasil = self.hitung_spec(formula.jenis_racik, n, bahan)
        hasil.update({"id_racikan": formula.id_racikan, "nama": formula.nama})
        return hasil

    def hitung_spec(self, jenis_racik: str, jumlah_unit: int, bahan_spec: list[dict]) -> dict:
        """Hitung dari SPEC mentah — dipakai formula maupun racikan ad-hoc di SOAP.

        bahan_spec: [{id_produk, dosis, satuan}] — satuan gr/g/ml → mode GRAM (pro-rata),
        selain itu mode MG (butir dibulatkan KE ATAS).
        """
        n = max(1, int(jumlah_unit or 1))
        rincian, subtotal, masalah = [], Decimal("0"), []

        for b in bahan_spec:
            produk = self.db.get(MasterProduk, b.get("id_produk")) if b.get("id_produk") else None
            if produk is None:
                masalah.append("Ada bahan yang produknya tidak ditemukan.")
                continue
            dosis = Decimal(str(b.get("dosis") or 0))
            if dosis <= 0:
                masalah.append(f"{produk.nama_produk}: dosis per unit belum diisi.")
                continue
            harga_jual = Decimal(str(produk.harga_jual or 0))
            satuan = (b.get("satuan") or "mg").lower()
            total_dosis = dosis * n

            if satuan in _SATUAN_GRAM:
                # Mode GRAM/krim → PRO-RATA per gram, tanpa pembulatan ke kemasan.
                isi = Decimal(str(produk.isi_kemasan or 0))
                if isi <= 0:
                    masalah.append(f"{produk.nama_produk}: isi kemasan belum diisi.")
                    continue
                harga_per_satuan = harga_jual / isi
                dipakai = total_dosis
                sub = _rp(total_dosis * harga_per_satuan)
                basis = f"{isi} {produk.satuan_isi or ''}".strip()
            else:
                # Mode MG/tablet → butir dibulatkan KE ATAS, ditagih penuh.
                kekuatan = Decimal(str(produk.kekuatan_nilai or 0))
                if kekuatan <= 0:
                    masalah.append(f"{produk.nama_produk}: kekuatan sediaan belum diisi.")
                    continue
                butir_raw = total_dosis / kekuatan
                dipakai = Decimal(str(math.ceil(butir_raw)))
                harga_per_satuan = harga_jual
                sub = _rp(dipakai * harga_jual)
                basis = f"{kekuatan} {produk.kekuatan_satuan or 'mg'}/butir"

            subtotal += sub
            rincian.append({
                "id_racikan_bahan": b.get("id_racikan_bahan"),
                "id_produk": produk.id_produk,
                "nama": produk.nama_produk,
                "kode_produk": produk.kode_produk,
                "dosis_per_unit": float(dosis),
                "satuan_dosis": satuan,
                "mode": "GRAM" if satuan in _SATUAN_GRAM else "MG",
                "basis": basis,
                "kekuatan_snapshot": float(isi if satuan in _SATUAN_GRAM else kekuatan),
                "total_dosis": float(total_dosis),
                "dipakai": float(dipakai),
                "satuan_dipakai": (produk.satuan_isi or "gr") if satuan in _SATUAN_GRAM else "butir",
                "harga_satuan": float(_rp(harga_per_satuan)),
                "subtotal": float(sub),
            })

        jenis = (jenis_racik or "").upper()
        tarif = self.tarif_racik(jenis)
        total = _rp(subtotal + tarif)
        return {
            "id_racikan": None,
            "nama": "",
            "jenis_racik": jenis,
            "jumlah_unit": n,
            "rincian": rincian,
            "subtotal_bahan": float(_rp(subtotal)),
            "biaya_racik": float(tarif),
            "total": float(total),
            "per_unit": float(_rp(total / n)) if n else 0.0,
            "masalah": masalah,
        }

    # ------------------------------------------- SNAPSHOT RESEP RACIKAN (SOAP)
    def save_kunjungan_racikan(self, id_kunjungan: int, racikan_list: list[dict]) -> None:
        """Replace semua racikan pada kunjungan dengan snapshot hasil hitung.

        racikan_list: [{id_racikan|None, nama, jenis_racik, jumlah_unit, aturan_pakai,
                        bahan: [{id_produk, dosis, satuan}]}]
        Harga DIKUNCI di sini — kasir tidak menghitung ulang.
        """
        # Hapus lama. WAJIB bulk DELETE berurutan (anak dulu, baru induk):
        # session.delete() per objek membiarkan SQLAlchemy mengurutkan sendiri, dan
        # karena kedua tabel ini tidak dihubungkan relationship(), induk bisa terhapus
        # lebih dulu → ditolak foreign key → seluruh transaksi rollback tanpa jejak.
        old_ids = self.db.execute(
            select(KunjunganRacikan.id_kunjungan_racikan)
            .where(KunjunganRacikan.id_kunjungan == id_kunjungan)
        ).scalars().all()
        if old_ids:
            self.db.execute(
                sa_delete(KunjunganRacikanBahan)
                .where(KunjunganRacikanBahan.id_kunjungan_racikan.in_(old_ids))
            )
            self.db.execute(
                sa_delete(KunjunganRacikan)
                .where(KunjunganRacikan.id_kunjungan_racikan.in_(old_ids))
            )
            self.db.flush()

        for r in racikan_list:
            bahan = r.get("bahan") or []
            if not bahan:
                continue
            h = self.hitung_spec(r.get("jenis_racik"), r.get("jumlah_unit"), bahan)
            if not h["rincian"]:
                import logging as _lg
                _lg.getLogger("sehati.racik").warning(
                    "RACIK-DILEWATI nama=%r bahan=%s masalah=%s",
                    r.get("nama"), bahan, h.get("masalah"),
                )
                continue
            head = KunjunganRacikan(
                id_kunjungan=id_kunjungan,
                id_racikan=r.get("id_racikan") or None,
                nama_snapshot=(r.get("nama") or "Racikan")[:100],
                jenis_racik=h["jenis_racik"],
                jumlah_unit=h["jumlah_unit"],
                aturan_pakai=(r.get("aturan_pakai") or None),
                subtotal_bahan=h["subtotal_bahan"],
                biaya_racik=h["biaya_racik"],
                total=h["total"],
                status_item="PENDING",
            )
            self.db.add(head)
            self.db.flush()
            for d in h["rincian"]:
                self.db.add(KunjunganRacikanBahan(
                    id_kunjungan_racikan=head.id_kunjungan_racikan,
                    id_produk=d["id_produk"],
                    nama_snapshot=d["nama"][:100],
                    dosis_per_unit=d["dosis_per_unit"],
                    satuan_dosis=d["satuan_dosis"],
                    kekuatan_snapshot=d["kekuatan_snapshot"],
                    mode_hitung=d["mode"],
                    dipakai=d["dipakai"],
                    satuan_dipakai=d["satuan_dipakai"],
                    harga_satuan=d["harga_satuan"],
                    subtotal=d["subtotal"],
                ))
        self.db.flush()

    def get_kunjungan_racikan(self, id_kunjungan: int) -> list[dict]:
        """Racikan tersimpan pada kunjungan (untuk mode Ubah SOAP, kasir, cetak)."""
        out = []
        for h in self.db.execute(
            select(KunjunganRacikan)
            .where(KunjunganRacikan.id_kunjungan == id_kunjungan)
            .order_by(KunjunganRacikan.id_kunjungan_racikan)
        ).scalars().all():
            bahan = [{
                "nama": b.nama_snapshot,
                "dosis_per_unit": float(b.dosis_per_unit),
                "satuan_dosis": b.satuan_dosis,
                "dipakai": float(b.dipakai),
                "satuan_dipakai": b.satuan_dipakai,
                "harga_satuan": float(b.harga_satuan),
                "subtotal": float(b.subtotal),
                "mode": b.mode_hitung,
                "id_produk": b.id_produk,
            } for b in self.db.execute(
                select(KunjunganRacikanBahan)
                .where(KunjunganRacikanBahan.id_kunjungan_racikan == h.id_kunjungan_racikan)
                .order_by(KunjunganRacikanBahan.id_kunjungan_racikan_bahan)
            ).scalars().all()]
            out.append({
                "id_kunjungan_racikan": h.id_kunjungan_racikan,
                "id_racikan": h.id_racikan,
                "nama": h.nama_snapshot,
                "jenis_racik": h.jenis_racik,
                "jumlah_unit": h.jumlah_unit,
                "aturan_pakai": h.aturan_pakai or "",
                "subtotal_bahan": float(h.subtotal_bahan),
                "biaya_racik": float(h.biaya_racik),
                "total": float(h.total),
                "status_item": h.status_item,
                "bahan": bahan,
            })
        return out
