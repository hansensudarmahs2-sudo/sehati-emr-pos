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
        jenis_awal = (jenis_racik or "").upper()
        # KRIM tidak punya konsep "butir": yang ditulis dokter adalah TOTAL gram dalam
        # satu pot, jadi tidak boleh dikalikan jumlah unit. Sebelumnya kartu memberi
        # default 15 (warisan kapsul) → menulis 8 gram menghasilkan 120 gram dan tagihan
        # membengkak 15x tanpa tanda apa pun. Keputusan dr. Hansen 2026-09-21.
        n = 1 if jenis_awal == "KRIM" else max(1, int(jumlah_unit or 1))
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

            # Pagar kewajaran — memperingatkan, TIDAK memblokir (pola sama dengan
            # peringatan stok minus). Tujuannya menangkap salah ketik sebelum jadi tagihan.
            if satuan in _SATUAN_GRAM and dipakai > Decimal("50"):
                masalah.append(
                    f"{produk.nama_produk}: {dipakai:g} gram — lebih dari satu pot biasa. "
                    f"Pastikan ini benar."
                )
            elif satuan not in _SATUAN_GRAM and dipakai > Decimal("200"):
                masalah.append(
                    f"{produk.nama_produk}: {dipakai:g} butir — jumlah tidak biasa. "
                    f"Pastikan ini benar."
                )

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
    def build_card_ctx(self, token: str, cur: dict, bahan_rows: list[dict],
                       endpoint: str = "/web/dokter/_racik-hitung") -> dict:
        """Context untuk merender satu Kartu Racik.

        `endpoint` membuat kartu yang sama bisa dipakai di SOAP dokter MAUPUN di layar
        tebus resep apotek — masing-masing punya rute hitung-ulang sendiri karena hak
        aksesnya berbeda, tapi kartunya satu berkas.
        """
        from app.services.master_produk_service import MasterProdukService

        spec = [
            {"id_produk": r["id_produk"], "dosis": r["dosis"], "satuan": r["satuan"]}
            for r in bahan_rows if r.get("id_produk")
        ]
        return {
            "token": token, "cur": cur, "bahan_rows": bahan_rows,
            "hitung": self.hitung_spec(cur.get("jenis"), cur.get("unit"), spec),
            "formulas": self.list_formula(only_active=True),
            "jenis_opts": self.list_biaya_racik(),
            "master_produks": MasterProdukService(self.db).list_all(
                only_active=True, limit=500),
            "racik_endpoint": endpoint,
        }

    def parse_card_form(self, form, token: str) -> tuple[dict, list[dict]]:
        """Baca SATU kartu (token tertentu) dari form hitung-ulang → (cur, bahan_rows).

        Dipakai bersama oleh rute hitung-ulang dokter dan apotek. Jangan disalin:
        di sinilah dulu lahir bug "kartu tertukar identitas".
        """
        def g(suffix, default=""):
            return (form.get(f"f_{token}_{suffix}") or default)

        id_racikan = (g("id_racikan") or "").strip()
        prev_formula = (g("prev_formula") or "").strip()
        try:
            unit = int(g("unit", "15") or 15)
        except (ValueError, TypeError):
            unit = 15
        _jenis = (g("jenis", "KAPSUL") or "KAPSUL").upper()
        cur = {
            "id_racikan": id_racikan, "nama": g("nama").strip(),
            "jenis": _jenis,
            # KRIM: penulis resep menulis TOTAL gram per pot, tidak ada pengali unit.
            "unit": 1 if _jenis == "KRIM" else max(1, unit),
            "aturan": g("aturan").strip(),
            # #51: identitas baris DB harus IKUT setiap kali kartu dirender ulang.
            # Kalau hilang di sini, kartu lama lahir kembali sebagai baris baru dan
            # baris aslinya dianggap dibuang dokter.
            "id_kunjungan_racikan": (g("id_kr") or "").strip(),
        }

        # Formula baru dipilih → muat komposisinya (menimpa isian bahan saat ini).
        if id_racikan and id_racikan != prev_formula:
            try:
                f = self.get_formula(int(id_racikan))
                cur["nama"] = f.nama
                cur["jenis"] = f.jenis_racik
                cur["unit"] = f.default_jumlah_unit or cur["unit"]
                cur["aturan"] = f.default_aturan_pakai or cur["aturan"]
                bahan_rows = [
                    {"id_produk": str(b.id_produk), "dosis": float(b.dosis_per_unit),
                     "satuan": b.satuan_dosis}
                    for b in self.list_bahan(f.id_racikan)
                ]
            except HTTPException:
                bahan_rows = []
            return cur, bahan_rows

        produk_l = form.getlist(f"b_{token}_produk")
        dosis_l = form.getlist(f"b_{token}_dosis")
        satuan_l = form.getlist(f"b_{token}_satuan")
        bahan_rows = []
        for i, pid in enumerate(produk_l):
            if not str(pid).strip():
                continue   # baris kosong diabaikan; template selalu menambah satu baris kosong
            bahan_rows.append({
                "id_produk": str(pid).strip(),
                "dosis": (dosis_l[i] if i < len(dosis_l) else ""),
                "satuan": (satuan_l[i] if i < len(satuan_l) else "mg"),
            })
        return cur, bahan_rows

    @staticmethod
    def parse_form_racikan(form_data) -> list[dict]:
        """Ubah isian Kartu Racik di form menjadi `racikan_list` untuk disimpan.

        DIPAKAI BERSAMA oleh SOAP dokter dan layar tebus resep apotek. Sengaja di sini,
        bukan disalin di tiap route: penguraian token kartu inilah yang dulu melahirkan
        tiga bug berturut-turut (token kembar dari cache browser, token tertukar karena
        dikirim lewat body, kartu ganda). Dua salinan yang berbeda pelan-pelan akan
        mengulang salah satunya.

        Aturan yang dipertahankan:
        - `rc_token` kembar dilewati — kartunya sama, jangan dihitung dua kali.
        - Bahan tanpa dosis (> 0) diabaikan; kartu tanpa bahan sama sekali dibuang.
        - KRIM tidak punya pengali unit (ditangani `hitung_spec`), di sini `unit`
          diambil apa adanya dari form.
        """
        out: list[dict] = []
        seen: set[str] = set()
        for t in form_data.getlist("rc_token"):
            t = (t or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            pl = form_data.getlist(f"b_{t}_produk")
            dl = form_data.getlist(f"b_{t}_dosis")
            sl = form_data.getlist(f"b_{t}_satuan")
            bahan = []
            for i, pid in enumerate(pl):
                if not str(pid).strip():
                    continue
                try:
                    idp = int(pid)
                except (ValueError, TypeError):
                    continue
                try:
                    dos = float(dl[i]) if i < len(dl) and str(dl[i]).strip() else 0
                except (ValueError, TypeError):
                    dos = 0
                if dos <= 0:
                    continue
                bahan.append({
                    "id_produk": idp, "dosis": dos,
                    "satuan": (sl[i] if i < len(sl) else "mg") or "mg",
                })
            if not bahan:
                continue
            try:
                unit = int(form_data.get(f"f_{t}_unit") or 1)
            except (ValueError, TypeError):
                unit = 1
            idr = (form_data.get(f"f_{t}_id_racikan") or "").strip()
            # #51: identitas BARIS DB asal kartu ini (bukan id formula master). Kosong =
            # kartu baru. Tanpa ini, simpan terpaksa hapus-semua-lalu-tulis-ulang, dan
            # halaman basi menghapus racikan yang lahir sesudahnya.
            _idkr = (form_data.get(f"f_{t}_id_kr") or "").strip()
            out.append({
                "id_kunjungan_racikan": int(_idkr) if _idkr.isdigit() else None,
                "id_racikan": int(idr) if idr.isdigit() else None,
                "nama": (form_data.get(f"f_{t}_nama") or "").strip() or "Racikan",
                "jenis_racik": (form_data.get(f"f_{t}_jenis") or "KAPSUL").upper(),
                "jumlah_unit": max(1, unit),
                "aturan_pakai": (form_data.get(f"f_{t}_aturan") or "").strip() or None,
                "bahan": bahan,
            })
        return out

    def save_kunjungan_racikan(self, id_kunjungan: int, racikan_list: list[dict],
                               loaded_ids: Optional[list[int]] = None) -> dict:
        """Simpan racikan PENDING kunjungan dari kartu di layar. Return ringkasan.

        racikan_list: [{id_kunjungan_racikan|None, id_racikan|None, nama, jenis_racik,
                        jumlah_unit, aturan_pakai, bahan: [{id_produk, dosis, satuan}]}]

        `loaded_ids` = id racikan PENDING yang TERLIHAT saat halaman SOAP dimuat (task #51).

        ======================= ATURAN INTI: JANGAN HAPUS YANG TAK KAULIHAT ===============
        Sebelum #51, fungsi ini menghapus SELURUH baris PENDING kunjungan lalu menulis
        ulang dari kartu di layar. Halaman basi (tab lama / tablet lain / dokter lain)
        punya kartu lebih sedikit, jadi "tulis ulang" berarti "hapus yang tidak kulihat" —
        termasuk racikan yang lahir SETELAH halaman itu dibuka. Hilang tanpa peringatan.

        Dengan `loaded_ids`:
          - yang dihapus = `loaded_ids` − id yang dikirim kartu
          - baris PENDING yang TIDAK ada di `loaded_ids` = lahir setelah halaman dimuat
            → DIPERTAHANKAN, dan jumlahnya dilaporkan lewat `dipertahankan` supaya
              pemanggil bisa memberi tahu dokter. Menyelamatkan data diam-diam tetap
              membingungkan.

        `loaded_ids=None` berarti pemanggil TIDAK tahu apa yang terlihat (mis. layar tebus
        resep apotek yang selalu membuat kunjungan BARU dan kosong). Dalam hal itu perilaku
        lama dipakai: semua PENDING diganti. Aman di sana justru karena kunjungannya baru.

        PAGAR LAMA TETAP: racikan DIBAYAR / BATAL / DITUNDA tidak pernah disentuh. R8
        bergantung pada ini — baris DITUNDA selamat justru karena saringan PENDING.
        """
        _tahu_yang_terlihat = loaded_ids is not None
        _terlihat = {int(x) for x in (loaded_ids or [])}
        # id baris yang kartunya masih ada di layar (kartu lama yang dipertahankan dokter)
        _dikirim = {
            int(r["id_kunjungan_racikan"]) for r in racikan_list
            if r.get("id_kunjungan_racikan")
        }

        semua_pending = set(self.db.execute(
            select(KunjunganRacikan.id_kunjungan_racikan)
            .where(
                KunjunganRacikan.id_kunjungan == id_kunjungan,
                KunjunganRacikan.status_item == "PENDING",
            )
        ).scalars().all())

        if _tahu_yang_terlihat:
            # Dibuang dokter di layar ini = terlihat saat dimuat, tapi kartunya tidak
            # dikirim balik. Baris di luar `_terlihat` sengaja TIDAK ikut.
            old_ids = list((_terlihat & semua_pending) - _dikirim)
            dipertahankan = sorted(semua_pending - _terlihat)
        else:
            old_ids = list(semua_pending)
            dipertahankan = []

        # Hapus. WAJIB bulk DELETE berurutan (anak dulu, baru induk):
        # session.delete() per objek membiarkan SQLAlchemy mengurutkan sendiri, dan
        # karena kedua tabel ini tidak dihubungkan relationship(), induk bisa terhapus
        # lebih dulu → ditolak foreign key → seluruh transaksi rollback tanpa jejak.
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

        n_baru = n_ubah = 0
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

            # #51: kartu yang membawa id → PERBARUI baris itu, jangan lahirkan baris baru.
            # Sebelumnya tiap simpan melahirkan id baru, itulah sebabnya "ID racikan
            # PENDING berubah tiap simpan" tercatat sebagai gejala sejak 2026-09-21.
            # Identitas yang stabil juga membuat jejak audit masuk akal.
            head = None
            _id_lama = r.get("id_kunjungan_racikan")
            if _id_lama:
                head = self.db.get(KunjunganRacikan, int(_id_lama))
                # Jangan percaya id dari form begitu saja: ia harus milik kunjungan ini
                # DAN masih PENDING. Kalau tidak, perlakukan sebagai kartu baru.
                if head is not None and (head.id_kunjungan != id_kunjungan
                                         or head.status_item != "PENDING"):
                    head = None

            if head is not None:
                head.id_racikan = r.get("id_racikan") or None
                head.nama_snapshot = (r.get("nama") or "Racikan")[:100]
                head.jenis_racik = h["jenis_racik"]
                head.jumlah_unit = h["jumlah_unit"]
                head.aturan_pakai = (r.get("aturan_pakai") or None)
                head.subtotal_bahan = h["subtotal_bahan"]
                head.biaya_racik = h["biaya_racik"]
                head.total = h["total"]
                # Bahan WAJIB ditulis ulang — `dipakai` bergantung jumlah unit.
                self.db.execute(
                    sa_delete(KunjunganRacikanBahan)
                    .where(KunjunganRacikanBahan.id_kunjungan_racikan
                           == head.id_kunjungan_racikan)
                )
                self.db.flush()
                n_ubah += 1
            else:
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
                n_baru += 1

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
        return {"baru": n_baru, "diubah": n_ubah, "dihapus": len(old_ids),
                "dipertahankan": dipertahankan}

    def pecah_racikan(self, id_kunjungan_racikan: int, unit_ditunda: int) -> dict:
        """R8 — pecah satu racikan PENDING jadi dua batch: yang ditagih & yang ditunda.

        [Keputusan dr. Hansen 2026-09-27] "racikan 15 butir, lalu minta menyisakan, maka
        akan popup service racik lagi dan input 10, dan tersisa 5 juga langsung masuk
        perhitungan racikan berikutnya. untuk harga jelas pasien akan membayar 50rb lebih
        mahal karena tiap racikan terkena biaya 50 ribu untuk biaya racik."

        ONGKOS RACIK GANDA ITU BENAR, BUKAN BUG. Meracik 10 lalu meracik 5 di lain hari
        adalah DUA pekerjaan meracik. Jangan "diperbaiki" jadi satu ongkos — itu justru
        membuat klinik menanggung kerja yang tidak dibayar.

        Kedua batch DIHITUNG ULANG penuh (`hitung_spec`), termasuk baris bahannya: jumlah
        butir yang dipakai bergantung pada jumlah unit, jadi menyalin baris bahan lama apa
        adanya akan salah.

        ⚠ Pecahan TIDAK memakai `id_kunjungan_racikan_asal` — kolom itu berarti "salinan
        yang dibuat saat penebusan" dan dipakai sebagai penanda anti-tebus-ganda. Lihat
        alasan lengkapnya di `kasir_service.tunda_item_resep`.
        """
        rc = self.db.get(KunjunganRacikan, id_kunjungan_racikan)
        if rc is None:
            raise HTTPException(404, f"Racikan {id_kunjungan_racikan} tidak ditemukan.")
        if rc.status_item != "PENDING":
            raise HTTPException(
                400, f"Racikan berstatus '{rc.status_item}' — hanya PENDING yang bisa dipecah.")

        _total_unit = int(rc.jumlah_unit or 0)
        unit_ditunda = int(unit_ditunda)
        if (rc.jenis_racik or "").upper() == "KRIM":
            raise HTTPException(
                400,
                "Racikan KRIM tidak bisa dipecah jumlahnya — isinya satu pot, dan "
                "gramnya sudah ditulis sebagai total. Sisakan seluruhnya atau tidak "
                "sama sekali.",
            )
        if not (0 < unit_ditunda < _total_unit):
            raise HTTPException(
                400,
                f"Jumlah yang disisakan harus antara 1 dan {_total_unit - 1}. "
                f"Kalau mau menyisakan semuanya, kosongkan kotaknya.",
            )

        bahan_lama = self.db.execute(
            select(KunjunganRacikanBahan)
            .where(KunjunganRacikanBahan.id_kunjungan_racikan == id_kunjungan_racikan)
            .order_by(KunjunganRacikanBahan.id_kunjungan_racikan_bahan.asc())
        ).scalars().all()
        spec = [
            {"id_produk": b.id_produk, "dosis": float(b.dosis_per_unit or 0),
             "satuan": b.satuan_dosis}
            for b in bahan_lama
        ]
        if not spec:
            raise HTTPException(400, "Racikan ini tidak punya bahan — tidak bisa dipecah.")

        _sisa_unit = _total_unit - unit_ditunda
        h_tagih = self.hitung_spec(rc.jenis_racik, _sisa_unit, spec)
        h_tunda = self.hitung_spec(rc.jenis_racik, unit_ditunda, spec)
        for _h in (h_tagih, h_tunda):
            if not _h["rincian"]:
                raise HTTPException(
                    400,
                    "Racikan tidak bisa dipecah: "
                    + "; ".join(_h.get("masalah") or ["bahan tidak lagi tersedia"]),
                )

        def _tulis_bahan(id_head: int, hasil: dict) -> None:
            for d in hasil["rincian"]:
                self.db.add(KunjunganRacikanBahan(
                    id_kunjungan_racikan=id_head,
                    id_produk=d["id_produk"], nama_snapshot=d["nama"][:100],
                    dosis_per_unit=d["dosis_per_unit"], satuan_dosis=d["satuan_dosis"],
                    kekuatan_snapshot=d["kekuatan_snapshot"], mode_hitung=d["mode"],
                    dipakai=d["dipakai"], satuan_dipakai=d["satuan_dipakai"],
                    harga_satuan=d["harga_satuan"], subtotal=d["subtotal"],
                ))

        # --- Batch yang DITAGIH hari ini: baris asli, dihitung ulang seutuhnya.
        # Baris bahannya WAJIB diganti — `dipakai` bergantung pada jumlah unit.
        self.db.execute(
            sa_delete(KunjunganRacikanBahan)
            .where(KunjunganRacikanBahan.id_kunjungan_racikan == id_kunjungan_racikan)
        )
        self.db.flush()
        rc.jumlah_unit = h_tagih["jumlah_unit"]
        rc.subtotal_bahan = h_tagih["subtotal_bahan"]
        rc.biaya_racik = h_tagih["biaya_racik"]
        rc.total = h_tagih["total"]
        _tulis_bahan(rc.id_kunjungan_racikan, h_tagih)

        # --- Batch yang DITUNDA: baris baru, saudara (bukan salinan penebusan).
        pecahan = KunjunganRacikan(
            id_kunjungan=rc.id_kunjungan,
            id_racikan=rc.id_racikan,
            nama_snapshot=rc.nama_snapshot,
            jenis_racik=h_tunda["jenis_racik"],
            jumlah_unit=h_tunda["jumlah_unit"],
            aturan_pakai=rc.aturan_pakai,
            subtotal_bahan=h_tunda["subtotal_bahan"],
            biaya_racik=h_tunda["biaya_racik"],
            total=h_tunda["total"],
            status_item="DITUNDA",
        )
        self.db.add(pecahan)
        self.db.flush()
        _tulis_bahan(pecahan.id_kunjungan_racikan, h_tunda)
        self.db.flush()

        return {
            "id_asal": rc.id_kunjungan_racikan,
            "unit_ditagih": h_tagih["jumlah_unit"], "total_ditagih": h_tagih["total"],
            "id_pecahan": pecahan.id_kunjungan_racikan,
            "unit_ditunda": h_tunda["jumlah_unit"], "total_ditunda": h_tunda["total"],
            "biaya_racik_ekstra": h_tunda["biaya_racik"],
        }

    def salin_racikan_ke_kunjungan(self, id_kunjungan_baru: int,
                                   id_racikan_asal_list: list[int]) -> int:
        """R8 — salin racikan PENDING/DITUNDA ke kunjungan penebusan. Return jumlah.

        HARGA DIHITUNG ULANG dengan harga bahan HARI INI (keputusan dr. Hansen
        2026-09-27), BUKAN menyalin snapshot lama. Ini pengecualian sadar atas aturan
        snapshot kelas `KunjunganRacikan`, dan hanya sah karena baris asal **belum pernah
        ditagih**. Baris DIBAYAR tidak boleh masuk ke sini — dijaga oleh filter status.

        Salinannya menunjuk asalnya lewat `id_kunjungan_racikan_asal`; keberadaan salinan
        itulah penanda "sudah ditebus" (pola sama dengan `kunjungan_resep.id_resep_asal`).
        """
        if not id_racikan_asal_list:
            return 0

        asal_rows = self.db.execute(
            select(KunjunganRacikan)
            .where(
                KunjunganRacikan.id_kunjungan_racikan.in_(id_racikan_asal_list),
                KunjunganRacikan.status_item.in_(["PENDING", "DITUNDA"]),
            )
        ).scalars().all()

        n = 0
        for asal in asal_rows:
            # Sudah pernah disalin? Jangan ditebus dua kali.
            sudah = self.db.execute(
                select(KunjunganRacikan.id_kunjungan_racikan)
                .where(KunjunganRacikan.id_kunjungan_racikan_asal
                       == asal.id_kunjungan_racikan)
                .limit(1)
            ).scalar_one_or_none()
            if sudah is not None:
                continue

            bahan_lama = self.db.execute(
                select(KunjunganRacikanBahan)
                .where(KunjunganRacikanBahan.id_kunjungan_racikan
                       == asal.id_kunjungan_racikan)
                .order_by(KunjunganRacikanBahan.id_kunjungan_racikan_bahan.asc())
            ).scalars().all()
            spec = [
                {"id_produk": b.id_produk, "dosis": float(b.dosis_per_unit or 0),
                 "satuan": b.satuan_dosis}
                for b in bahan_lama
            ]
            if not spec:
                continue

            h = self.hitung_spec(asal.jenis_racik, asal.jumlah_unit, spec)
            if not h["rincian"]:
                # Bahan bisa sudah dinonaktifkan/dihapus sejak diresepkan. Jangan diam:
                # apoteker harus tahu agar bisa menawarkan pengganti ke pasien.
                raise HTTPException(
                    400,
                    f"Racikan {asal.nama_snapshot!r} tidak bisa ditebus: "
                    + "; ".join(h.get("masalah") or ["bahan tidak lagi tersedia"]),
                )

            head = KunjunganRacikan(
                id_kunjungan=id_kunjungan_baru,
                id_racikan=asal.id_racikan,
                nama_snapshot=asal.nama_snapshot,
                jenis_racik=h["jenis_racik"],
                jumlah_unit=h["jumlah_unit"],
                aturan_pakai=asal.aturan_pakai,
                subtotal_bahan=h["subtotal_bahan"],
                biaya_racik=h["biaya_racik"],
                total=h["total"],
                status_item="PENDING",
                id_kunjungan_racikan_asal=asal.id_kunjungan_racikan,
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
            n += 1
        self.db.flush()
        return n

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
