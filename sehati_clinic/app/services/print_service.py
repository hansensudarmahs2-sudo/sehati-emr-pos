"""
PrintService — context builder untuk render Nota Kasir + Resume Medis SOAP.

Read-only — fetch + format saja. Audit log ditulis di sini (PRINT_NOTA / PRINT_SOAP)
karena setiap render = 1 event cetak yang trackable.

Reference: DEC-047 (Print Module Path A) + PrintModule/00_DESIGN.md.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.audit_service import AuditService
from app.services.klinik_config_service import KlinikConfigService, VALID_PAPER_SIZES


class PrintService:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # NOTA KASIR
    # =========================================================================
    def prepare_nota_context(
        self,
        id_transaksi: int,
        paper: str = "a5",
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> dict[str, Any]:
        """
        Fetch transaksi + child entities + klinik config untuk render nota.

        Returns dict siap dipassing ke Jinja2 template:
            {
                "klinik": {...config...},
                "transaksi": {...header...},
                "pasien": {...nama, no_rm...},
                "kasir_nama": str,
                "items": [{tipe, label, qty, harga, subtotal}, ...],
                "subtotal": float,
                "diskon": float,
                "total": float,
                "pembayaran": [{metode, nominal}, ...],
                "total_bayar": float,
                "kembali": float,
                "paper": "a5" | "thermal",
                "tgl_cetak": str ISO,
            }
        """
        from app.db.models import (
            TransaksiKasir, TransaksiPembayaran,
            Kunjungan, Pasien, MasterStaf,
            KunjunganTindakan, MasterTreatment,
            KunjunganResep, MasterProduk,
            StatusTindakanEnum, StatusItemResepEnum,
            PemeriksaanKlinis,
        )

        if paper not in VALID_PAPER_SIZES:
            paper = "a5"

        # 1. Transaksi + kunjungan + pasien + kasir + dokter penanggung jawab
        from sqlalchemy.orm import aliased as _aliased
        _DokterStaf = _aliased(MasterStaf)
        row = self.db.execute(
            select(
                TransaksiKasir,
                Kunjungan.id_kunjungan,
                Kunjungan.tgl_kunjungan,
                Pasien.id_pasien, Pasien.no_rm, Pasien.nama,
                Pasien.tgl_lahir, Pasien.jenis_kelamin,
                MasterStaf.id_staf, MasterStaf.nama_staf,
                _DokterStaf.nama_staf.label("dokter_nama"),
            )
            .join(Kunjungan, Kunjungan.id_kunjungan == TransaksiKasir.id_kunjungan, isouter=True)
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien, isouter=True)
            .join(MasterStaf, MasterStaf.id_staf == TransaksiKasir.id_staf_kasir, isouter=True)
            .join(_DokterStaf, _DokterStaf.id_staf == Kunjungan.id_staf_dokter_assigned, isouter=True)
            .where(TransaksiKasir.id_transaksi == id_transaksi)
        ).first()

        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Transaksi #{id_transaksi} tidak ditemukan")

        (trx, id_kunj, tgl_kunj, id_pasien, no_rm, nama_pasien, tgl_lahir_pasien,
         jenis_kelamin_pasien, id_kasir, nama_kasir, dokter_nama) = row

        # M2/M3: transaksi MEMBERSHIP (id_kunjungan NULL) -> pasien via trx.id_pasien
        if id_pasien is None and getattr(trx, "id_pasien", None):
            _pm = self.db.get(Pasien, trx.id_pasien)
            if _pm is not None:
                id_pasien = _pm.id_pasien
                no_rm = _pm.no_rm
                nama_pasien = _pm.nama
                tgl_lahir_pasien = _pm.tgl_lahir
                jenis_kelamin_pasien = _pm.jenis_kelamin

        # Fallback tenaga medis: kalau tak ada dokter assigned, ambil dokter SOAP.
        if not dokter_nama and id_kunj:
            _soap = self.db.execute(
                select(MasterStaf.nama_staf)
                .select_from(PemeriksaanKlinis)
                .join(MasterStaf, MasterStaf.id_staf == PemeriksaanKlinis.id_staf_dokter, isouter=True)
                .where(PemeriksaanKlinis.id_kunjungan == id_kunj)
                .limit(1)
            ).scalar()
            dokter_nama = _soap

        # 2. Pembayaran (split-payment ready)
        pembayaran_rows = self.db.execute(
            select(TransaksiPembayaran)
            .where(TransaksiPembayaran.id_transaksi == id_transaksi)
            .order_by(TransaksiPembayaran.id_pembayaran)
        ).scalars().all()

        pembayaran_list = [
            {"metode": p.metode_bayar, "nominal": float(p.nominal or 0)}
            for p in pembayaran_rows
        ]
        total_bayar = sum(p["nominal"] for p in pembayaran_list)

        # 3. Items — tindakan SELESAI + resep DIBAYAR di kunjungan terkait
        # NOTA-C: Track kuota items secara terpisah supaya nota bisa tampilkan
        # "Diskon Benefit Member" sebagai line item terpisah, plus section
        # "Benefit Terpakai" untuk detail kuota yang dipakai.
        items = []
        benefit_items: list[dict[str, Any]] = []
        diskon_benefit = 0.0
        if id_kunj is not None:
            tindakan_rows = self.db.execute(
                select(KunjunganTindakan, MasterTreatment.nama_treatment, MasterTreatment.harga)
                .join(MasterTreatment, MasterTreatment.id_treatment == KunjunganTindakan.id_treatment)
                .where(KunjunganTindakan.id_kunjungan == id_kunj)
                .where(KunjunganTindakan.status_tindakan == StatusTindakanEnum.SELESAI)
                .order_by(KunjunganTindakan.id_kunjungan_tindakan)
            ).all()
            for kt, nama_t, harga in tindakan_rows:
                hg = float(harga or 0)
                _id_kuota_used = getattr(kt, "id_kuota_member", None)
                _is_kuota = _id_kuota_used is not None
                items.append({
                    "tipe": "TND",
                    "label": nama_t,
                    "qty": 1,
                    "harga": hg,
                    "subtotal": hg,
                    "pakai_kuota": _is_kuota,
                })
                if _is_kuota:
                    diskon_benefit += hg
                    # Enrich dengan tier + periode untuk section "Benefit Terpakai"
                    from app.db.models import (
                        PasienMembershipKuota as _PMK,
                        PasienMembershipHistory as _PMH,
                        MasterMembership as _MM,
                    )
                    tier_name = "?"
                    periode_str = "?"
                    try:
                        _kuota_row = self.db.get(_PMK, _id_kuota_used)
                        if _kuota_row is not None:
                            _pv = (
                                _kuota_row.periode_kuota.value
                                if hasattr(_kuota_row.periode_kuota, "value")
                                else str(_kuota_row.periode_kuota or "")
                            )
                            periode_str = _pv
                            if _kuota_row.bulan_periode:
                                periode_str = f"{_pv} {_kuota_row.bulan_periode}"
                            if _kuota_row.id_membership_history:
                                _hist = self.db.get(_PMH, _kuota_row.id_membership_history)
                                if _hist is not None:
                                    _tier = self.db.get(_MM, _hist.id_membership)
                                    if _tier is not None:
                                        tier_name = _tier.nama_tier
                    except Exception:
                        pass
                    benefit_items.append({
                        "nama_treatment": nama_t,
                        "tier": tier_name,
                        "periode": periode_str,
                        "nominal": hg,
                    })

            # Phase 4 (#364 DEC-063): kalau transaksi VOID, cascade FLOW-V6 sudah ubah
            # semua resep DIBAYAR → BATAL. Untuk nota void, include BATAL juga supaya
            # items asli tetap tampil (dengan watermark VOID di atas).
            _is_voided = getattr(trx, "status_transaksi", "BAYAR") == "VOID"
            _resep_status_filter = [StatusItemResepEnum.DIBAYAR]
            if _is_voided:
                _resep_status_filter.append(StatusItemResepEnum.BATAL)
            resep_rows = self.db.execute(
                select(KunjunganResep, MasterProduk.nama_produk, MasterProduk.harga_jual)
                .join(MasterProduk, MasterProduk.id_produk == KunjunganResep.id_produk)
                .where(KunjunganResep.id_kunjungan == id_kunj)
                .where(KunjunganResep.status_item.in_(_resep_status_filter))
                .order_by(KunjunganResep.id_resep)
            ).all()
            for kr, nama_p, harga in resep_rows:
                qty = float(kr.qty or 0)
                hg = float(harga or 0)
                items.append({
                    "tipe": "OBT",
                    "label": nama_p,
                    "qty": qty,
                    "harga": hg,
                    "subtotal": round(qty * hg, 2),
                })

            # Fase 3: racikan. Dibaca dari SNAPSHOT transaksi_detail_racikan (bukan dari
            # kunjungan_racikan) supaya nota lama tetap utuh walau racikannya diubah.
            # qty=1 karena satu baris = satu racikan utuh; jumlah unit masuk ke label.
            from app.db.models.racikan import TransaksiDetailRacikan as _TDR
            _racik_rows = self.db.execute(
                select(_TDR)
                .where(_TDR.id_transaksi == trx.id_transaksi)
                .order_by(_TDR.id_detail_racikan)
            ).scalars().all()
            for _dr in _racik_rows:
                _tot = float(_dr.subtotal_bahan or 0) + float(_dr.biaya_racik or 0)
                items.append({
                    "tipe": "RCK",
                    "label": f"{_dr.nama_snapshot} ({_dr.jenis_racik} {_dr.jumlah_unit} unit)",
                    "qty": 1,
                    "harga": _tot,
                    "subtotal": round(_tot, 2),
                })

        # M2/M3: transaksi MEMBERSHIP -> baris "Aktivasi Membership <tier>"
        if not items and getattr(trx, "id_membership_aktivasi", None):
            from app.db.models import MasterMembership as _MM_nota
            _tier_nota = self.db.get(_MM_nota, trx.id_membership_aktivasi)
            _nom_nota = float(trx.nominal_aktivasi_membership or trx.total_tagihan or 0)
            items.append({
                "tipe": "MBR",
                "label": f"Aktivasi Membership {_tier_nota.nama_tier if _tier_nota else ''}".strip(),
                "qty": 1,
                "harga": _nom_nota,
                "subtotal": _nom_nota,
            })

        # 4. Klinik config
        cfg = KlinikConfigService(self.db).get_config()
        klinik = self._klinik_dict(cfg)

        # 5. Subtotal, diskon, total, kembali
        # NOTA-C: pakai gross subtotal (sum of items at full price) supaya
        # diskon_benefit bisa ditampilkan terpisah. Math nota:
        #   subtotal_gross  −  diskon_member  −  diskon_benefit  =  total
        diskon = float(trx.nominal_diskon or 0)
        total = float(trx.total_tagihan or 0)
        subtotal_gross = round(sum(i["subtotal"] for i in items), 2) if items else 0.0
        subtotal = subtotal_gross if items else float(trx.subtotal or 0)
        kembali = max(0.0, round(total_bayar - total, 2))

        # 6. Audit log: PRINT_NOTA event
        self._audit_print(
            aksi="PRINT_NOTA",
            actor_id_staf=actor_id_staf,
            id_target=id_transaksi,
            tabel_target="transaksi_kasir",
            keterangan=f"paper={paper}, total={total}, items={len(items)}",
            request=request,
        )

        # Phase 4 (#364 DEC-063): VOID info untuk watermark + alasan
        is_voided = getattr(trx, "status_transaksi", "BAYAR") == "VOID"
        voided_by_nama = None
        if is_voided and getattr(trx, "void_by_id_staf", None):
            from app.db.models import MasterStaf as _MS
            voider = self.db.get(_MS, trx.void_by_id_staf)
            voided_by_nama = voider.nama_staf if voider else None

        # Task #54-F + T32: nota menampilkan TOTAL BERSIH (total transaksi − refund)
        # dan daftar pengembaliannya. Sejak T32 (2026-10-05) `total_tagihan` header
        # TIDAK lagi dikurangi refund — jadi pengurangannya dilakukan DI SINI, supaya
        # tampilan nota tetap sama dengan sebelumnya ("TOTAL sudah dikurangi
        # pengembalian"). `kembali` sengaja dihitung dari total BRUTO di atas: uang
        # kembalian terjadi saat bayar, sebelum ada refund. Dulu, dengan header yang
        # dimutasi, kembalian di nota cetak-ulang membesar setelah refund (audit T31).
        from app.db.models import TransaksiRefund as _TR
        _refund_rows = self.db.execute(
            select(_TR.nilai_refund, _TR.tgl_refund, _TR.metode_refund, _TR.alasan)
            .where(_TR.id_transaksi == trx.id_transaksi)
            .order_by(_TR.id_refund.asc())
        ).all()
        refund_items = [
            {
                "nilai": float(r.nilai_refund or 0),
                "tgl": r.tgl_refund,
                "metode": r.metode_refund or "—",
                "alasan": r.alasan or "",
            }
            for r in _refund_rows
        ]
        refund_total = round(sum(r["nilai"] for r in refund_items), 2)
        total = round(total - refund_total, 2)

        return {
            "klinik": klinik,
            "refund_items": refund_items,
            "refund_total": refund_total,
            "ada_refund": bool(refund_items),
            "transaksi": {
                "id_transaksi": int(trx.id_transaksi),
                "id_kunjungan": int(id_kunj) if id_kunj else None,
                "waktu_bayar": trx.waktu_bayar,
                "tgl_kunjungan": tgl_kunj,
                "keterangan_promo": trx.keterangan_promo,
            },
            "pasien": {
                "id_pasien": int(id_pasien) if id_pasien else None,
                "no_rm": no_rm or "—",
                "nama": nama_pasien or "—",
                "tgl_lahir": tgl_lahir_pasien,
                "jenis_kelamin": jenis_kelamin_pasien or "—",
            },
            "kasir_nama": nama_kasir or "—",
            "tenaga_medis": dokter_nama or "—",
            "items": items,
            "subtotal": subtotal,
            "diskon": diskon,
            "diskon_benefit": round(diskon_benefit, 2),
            "benefit_items": benefit_items,
            "total": total,
            "pembayaran": pembayaran_list,
            "total_bayar": total_bayar,
            "kembali": kembali,
            "paper": paper,
            "tgl_cetak": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "is_voided": is_voided,
            "void_at": getattr(trx, "void_at", None),
            "void_reason_code": getattr(trx, "void_reason_code", None),
            "void_reason_note": getattr(trx, "void_reason_note", None),
            "voided_by_nama": voided_by_nama,
            "late_void": bool(getattr(trx, "late_void", False)),
        }

    # =========================================================================
    # RESUME MEDIS SOAP
    # =========================================================================
    def prepare_soap_context(
        self,
        id_kunjungan: int,
        paper: str = "a5",
        actor_id_staf: Optional[int] = None,
        request: Optional[Request] = None,
    ) -> dict[str, Any]:
        """
        Fetch Kunjungan + Pasien + SOAP + tindakan + resep + dokter + klinik config
        untuk render Resume Medis.

        Returns dict siap dipassing ke Jinja2 template:
            {
                "klinik": {...config...},
                "kunjungan": {id_kunjungan, tgl_kunjungan, nomor_antrean},
                "pasien": {id_pasien, no_rm, nama, jenis_kelamin, tgl_lahir, umur_tahun},
                "dokter": {id_staf, nama_staf},
                "soap": {anamnesa, pemeriksaan_fisik, diagnosa,
                         saran_treatment, saran_produk, has_soap},
                "tindakan": [{nama_treatment, status, waktu_selesai}, ...],
                "resep": [{nama_produk, qty, aturan_pakai, status_item}, ...],
                "ttd_text": str (sign-off line dari klinik config),
                "paper": "a5" | "thermal",
                "tgl_cetak": str,
            }
        """
        from app.db.models import (
            Kunjungan, Pasien, MasterStaf,
            KunjunganTindakan, MasterTreatment,
            KunjunganResep, MasterProduk,
            PemeriksaanKlinis,
        )

        if paper not in VALID_PAPER_SIZES:
            paper = "a5"

        # 1. Kunjungan + pasien
        row = self.db.execute(
            select(Kunjungan, Pasien)
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
        ).first()

        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Kunjungan #{id_kunjungan} tidak ditemukan",
            )
        kunjungan, pasien = row

        # 2. SOAP (ambil yang terbaru kalau ada multiple — defensive)
        soap_row = self.db.execute(
            select(PemeriksaanKlinis)
            .where(PemeriksaanKlinis.id_kunjungan == id_kunjungan,
                   # Resume medis TIDAK boleh mencetak draf yang belum disetujui dokter.
                   PemeriksaanKlinis.status_soap == "FINAL")
            .order_by(PemeriksaanKlinis.id_pemeriksaan.desc())
            .limit(1)
        ).scalar_one_or_none()

        # 3. Dokter — prefer dari SOAP; fallback dari kunjungan.id_staf_input
        id_staf_dokter = None
        if soap_row and soap_row.id_staf_dokter:
            id_staf_dokter = soap_row.id_staf_dokter
        elif getattr(kunjungan, "id_staf_input", None):
            id_staf_dokter = kunjungan.id_staf_input

        nama_dokter = "—"
        if id_staf_dokter:
            staf_row = self.db.get(MasterStaf, id_staf_dokter)
            if staf_row:
                nama_dokter = staf_row.nama_staf or "—"

        # Asal-usul catatan: kalau SOAP ini semula draf apoteker dari konsultasi online,
        # resume medis WAJIB menyatakannya. Menghapus jejak itu membuat catatan tampak
        # seperti pemeriksaan langsung — dan resume medis justru dokumen yang paling
        # mungkin dibaca orang di luar klinik.
        soap_penyusun = None
        soap_waktu_konsultasi = getattr(soap_row, "waktu_konsultasi", None) if soap_row else None
        soap_waktu_disetujui = getattr(soap_row, "waktu_disetujui", None) if soap_row else None
        if soap_row and getattr(soap_row, "id_staf_penyusun", None):
            _p = self.db.get(MasterStaf, soap_row.id_staf_penyusun)
            soap_penyusun = _p.nama_staf if _p else None

        # 4. Tindakan diresepkan di kunjungan ini (semua status — supaya pasien tahu rencana)
        tindakan_rows = self.db.execute(
            select(KunjunganTindakan, MasterTreatment.nama_treatment)
            .join(MasterTreatment, MasterTreatment.id_treatment == KunjunganTindakan.id_treatment)
            .where(KunjunganTindakan.id_kunjungan == id_kunjungan)
            .order_by(KunjunganTindakan.id_kunjungan_tindakan)
        ).all()
        tindakan_list = []
        for kt, nama_t in tindakan_rows:
            status_t = (
                kt.status_tindakan.value
                if hasattr(kt.status_tindakan, "value")
                else (str(kt.status_tindakan) if kt.status_tindakan else "—")
            )
            tindakan_list.append({
                "nama_treatment": nama_t,
                "status": status_t,
                "waktu_selesai": kt.waktu_selesai,
            })

        # 5. Resep diresepkan (semua kecuali BATAL — supaya pasien tahu apa yang diresep).
        # R8: baris DITUNDA SENGAJA tetap ikut — ia benar-benar diresepkan, cuma belum
        # ditebus. Template menandainya "belum ditebus" supaya tidak terbaca seolah sudah
        # diserahkan. (Bandingkan nota kasir, yang justru memakai daftar-putih DIBAYAR.)
        from app.db.models import StatusItemResepEnum
        resep_rows = self.db.execute(
            select(KunjunganResep, MasterProduk.nama_produk)
            .join(MasterProduk, MasterProduk.id_produk == KunjunganResep.id_produk)
            .where(KunjunganResep.id_kunjungan == id_kunjungan)
            .where(KunjunganResep.status_item != StatusItemResepEnum.BATAL)
            .order_by(KunjunganResep.id_resep)
        ).all()
        resep_list = []
        for kr, nama_p in resep_rows:
            status_r = (
                kr.status_item.value
                if hasattr(kr.status_item, "value")
                else (str(kr.status_item) if kr.status_item else "—")
            )
            resep_list.append({
                "nama_produk": nama_p,
                "qty": float(kr.qty or 0),
                "aturan_pakai": kr.aturan_pakai or "",
                "status_item": status_r,
            })

        # 6. Klinik config + sign-off
        cfg = KlinikConfigService(self.db).get_config()
        klinik = self._klinik_dict(cfg)
        ttd_text = cfg.ttd_dokter_text or "Dokter Pemeriksa,"

        # 7. Umur pasien (jika tgl_lahir ada)
        umur_tahun = None
        if getattr(pasien, "tanggal_lahir", None):
            from datetime import date
            today = date.today()
            tl = pasien.tanggal_lahir
            umur_tahun = today.year - tl.year - ((today.month, today.day) < (tl.month, tl.day))

        # 8. Audit log PRINT_SOAP
        self._audit_print(
            aksi="PRINT_SOAP",
            actor_id_staf=actor_id_staf,
            id_target=id_kunjungan,
            tabel_target="kunjungan",
            keterangan=(
                f"paper={paper}, has_soap={soap_row is not None}, "
                f"tindakan={len(tindakan_list)}, resep={len(resep_list)}"
            ),
            request=request,
        )

        # 9. SOAP dict
        soap_dict = {
            "has_soap": soap_row is not None,
            "anamnesa": (soap_row.anamnesa if soap_row else "") or "",
            "pemeriksaan_fisik": (soap_row.pemeriksaan_fisik if soap_row else "") or "",
            "diagnosa": (soap_row.diagnosa if soap_row else "") or "",
            "saran_treatment": (soap_row.saran_treatment if soap_row else "") or "",
            "saran_produk": (soap_row.saran_produk if soap_row else "") or "",
        }

        jk = getattr(pasien, "jenis_kelamin", None)
        jenis_kelamin = (jk.value if hasattr(jk, "value") else (str(jk) if jk else "—"))

        return {
            "klinik": klinik,
            "kunjungan": {
                "id_kunjungan": int(kunjungan.id_kunjungan),
                "tgl_kunjungan": kunjungan.tgl_kunjungan,
                "nomor_antrean": getattr(kunjungan, "nomor_antrean", None),
            },
            "pasien": {
                "id_pasien": int(pasien.id_pasien),
                "no_rm": pasien.no_rm or "—",
                "nama": pasien.nama or "—",
                "jenis_kelamin": jenis_kelamin,
                "tanggal_lahir": getattr(pasien, "tanggal_lahir", None),
                "umur_tahun": umur_tahun,
            },
            "dokter": {
                "id_staf": int(id_staf_dokter) if id_staf_dokter else None,
                "nama_staf": nama_dokter,
            },
            "soap": soap_dict,
            # Asal-usul catatan (konsultasi online): dicetak apa adanya supaya pembaca
            # tahu ini disusun apoteker lalu disetujui dokter, bukan pemeriksaan langsung.
            "soap_penyusun": soap_penyusun,
            "soap_waktu_konsultasi": soap_waktu_konsultasi,
            "soap_waktu_disetujui": soap_waktu_disetujui,
            "tindakan": tindakan_list,
            "resep": resep_list,
            "ttd_text": ttd_text,
            "paper": paper,
            "tgl_cetak": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    # =========================================================================
    # HELPERS
    # =========================================================================
    def _klinik_dict(self, cfg) -> dict[str, Any]:
        """Helper: extract klinik config sebagai dict untuk template."""
        return {
            "nama_klinik": cfg.nama_klinik or "Klinik Anda",
            "alamat_baris1": cfg.alamat_baris1 or "",
            "alamat_baris2": cfg.alamat_baris2 or "",
            "alamat_baris3": cfg.alamat_baris3 or "",
            "no_telepon": cfg.no_telepon or "",
            "no_whatsapp": cfg.no_whatsapp or "",
            "email": cfg.email or "",
            "website": cfg.website or "",
            "logo_path": cfg.logo_path or "",
            "footer_text": cfg.footer_text or "",
        }

    # =========================================================================
    # NOMOR ANTRIAN (thermal) — NA-PRINT
    # =========================================================================
    def prepare_antrian_context(
        self,
        id_kunjungan: int,
        actor_id_staf=None,
        request: "Request | None" = None,
    ) -> "dict[str, Any]":
        """Context untuk cetak nomor antrian (thermal). Nomor = kunjungan.nomor_antrean.
        Reset harian otomatis (nomor dihitung MAX per-tanggal +1)."""
        from app.db.models import Kunjungan, Pasien
        cfg = KlinikConfigService(self.db).get_config()
        klinik = self._klinik_dict(cfg)
        row = self.db.execute(
            select(
                Kunjungan.nomor_antrean, Kunjungan.tgl_kunjungan, Kunjungan.status_antrian,
                Pasien.no_rm, Pasien.nama, Pasien.jenis_kelamin, Pasien.tgl_lahir,
            )
            .join(Pasien, Pasien.id_pasien == Kunjungan.id_pasien, isouter=True)
            .where(Kunjungan.id_kunjungan == id_kunjungan)
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Kunjungan #{id_kunjungan} tidak ditemukan")
        nomor, tgl_kunj, status_antrian, no_rm, nama, jk, tgl_lahir = row
        _TUJUAN = {"ANTRI_KONSULTASI": "Konsultasi", "KONSULTASI": "Konsultasi",
                   "ANTRI_TREATMENT": "Treatment", "ON_TREATMENT": "Treatment"}
        self._audit_print("PRINT_ANTRIAN", actor_id_staf, id_kunjungan, "kunjungan",
                          f"Cetak nomor antrian #{nomor}", request)
        return {
            "klinik": klinik,
            "nomor_antrean": nomor,
            "pasien": {"no_rm": no_rm, "nama": nama,
                       "jenis_kelamin": (jk.value if hasattr(jk, "value") else jk),
                       "tgl_lahir": tgl_lahir},
            "tujuan": _TUJUAN.get(status_antrian, "-"),
            "tgl_kunjungan": tgl_kunj,
            "tgl_cetak": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "paper": "thermal",
        }

    def _audit_print(
        self,
        aksi: str,
        actor_id_staf: Optional[int],
        id_target: int,
        tabel_target: str,
        keterangan: str,
        request: Optional[Request] = None,
    ) -> None:
        if actor_id_staf is None:
            return
        try:
            AuditService(self.db).log(
                aksi=aksi,
                id_staf=actor_id_staf,
                tabel_target=tabel_target,
                id_target=id_target,
                keterangan=keterangan,
                request=request,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()


__all__ = ["PrintService"]
