"""Pemeriksa bayar dulu tahap 4 — setiap tindakan yang DIBATALKAN SESUDAH DIBAYAR punya
pasangan, tepat satu jalur (spek DESAIN_BAYAR_DULU_BERCABANG.md §1: "setiap rupiah punya
pasangan"; rencana RENCANA_BAYAR_DULU_TAHAP4.md T4-6).

HANYA MEMBACA. Tidak menulis apa pun. Exit 1 bila ada temuan.

Kenapa ini perlu ada
--------------------
Tindakan yang dibayar di muka lalu tidak dikerjakan tidak boleh hilang begitu saja — uangnya
ada di omzet. Tahap 4 memberinya tiga jalan keluar, dan semuanya menulis `BATAL` di tindakan
sambil MEMBIARKAN `id_transaksi` (jejak pembayar):

  T4-1 Simpan sebagai hak  → audit `TINDAKAN_JADI_HAK` (bentuk HAK / KUOTA / SESI) dan,
                             untuk bentuk HAK, rencana PRABAYAR ber-`id_referensi_sumber`.
  T4-3 Kembalikan uang     → `transaksi_refund` jenis TINDAKAN ber-`id_kunjungan_tindakan`
                             (langsung, atau atas hak yang lahir di T4-1).

Tindakan BATAL ber-`id_transaksi` BAYAR tanpa pasangan = uang yang diterima klinik untuk
tindakan yang tak dikerjakan, tak dijadikan hak, dan tak dikembalikan — persis yang tahap 4
cegah. Kebalikannya juga dicek: refund TINDAKAN / hak PRABAYAR yang menunjuk tindakan yang
tidak BATAL atau bukan tindakan ber-transaksi itu.

Aturan per tindakan BATAL ber-`id_transaksi` di transaksi BAYAR
---------------------------------------------------------------
  - audit TINDAKAN_JADI_HAK: 0 atau 1 (lebih = disimpan dua kali);
  - bentuk HAK  → tepat 1 rencana PRABAYAR menunjuknya; KUOTA/SESI → 0 rencana PRABAYAR;
  - refund TINDAKAN: paling banyak 1; bentuk KUOTA tidak pernah direfund (Rp 0);
  - tanpa audit TINDAKAN_JADI_HAK → tepat 1 refund (refund langsung, T4-3 asal A);
  - kecuali: baris dengan `id_transaksi` di transaksi VOID tidak dinilai (void ditolak oleh
    pagar T4-4, jadi itu data lama — dilaporkan terpisah sebagai "tak dinilai").

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_tindakan_lunas_batal
Di laptop:  docker compose ... exec sehati-app python -m scripts.cek_tindakan_lunas_batal
"""
import sys
from collections import Counter, defaultdict
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session


def _bentuk(data) -> Optional[str]:
    if isinstance(data, dict):
        return data.get("bentuk")
    return None


def periksa(db: Session, ids: Optional[Iterable[int]] = None) -> dict:
    """{"temuan": [str], "tak_dinilai": [str], "dinilai": int}. `ids` = batasi ke tindakan
    tertentu (dipakai test, yang berjalan di DB bersama data lain)."""
    from app.db.models import (AuditLog, KunjunganTindakan, PasienRencanaTreatment,
                               TransaksiKasir, TransaksiRefund)
    from app.db.models._enums import SumberRencanaEnum

    ids = set(ids) if ids is not None else None
    q = (select(KunjunganTindakan.id_kunjungan_tindakan, KunjunganTindakan.id_transaksi,
                TransaksiKasir.status_transaksi)
         .join(TransaksiKasir, TransaksiKasir.id_transaksi == KunjunganTindakan.id_transaksi)
         .where(KunjunganTindakan.status_tindakan == "BATAL"))
    if ids is not None:
        q = q.where(KunjunganTindakan.id_kunjungan_tindakan.in_(ids or {-1}))
    batal = db.execute(q).all()

    def _filter(col):
        return [col.in_(ids or {-1})] if ids is not None else []

    hak = Counter(db.execute(
        select(PasienRencanaTreatment.id_referensi_sumber)
        .where(PasienRencanaTreatment.sumber_rencana == SumberRencanaEnum.PRABAYAR)
        .where(*_filter(PasienRencanaTreatment.id_referensi_sumber))).scalars())
    refund = Counter(db.execute(
        select(TransaksiRefund.id_kunjungan_tindakan)
        .where(TransaksiRefund.id_kunjungan_tindakan.is_not(None))
        .where(*_filter(TransaksiRefund.id_kunjungan_tindakan))).scalars())
    jadi_hak: dict[int, list] = defaultdict(list)
    for id_t, data in db.execute(
            select(AuditLog.id_target, AuditLog.data_baru)
            .where(AuditLog.aksi == "TINDAKAN_JADI_HAK")
            .where(AuditLog.tabel_target == "kunjungan_tindakan")
            .where(*_filter(AuditLog.id_target))).all():
        jadi_hak[int(id_t)].append(_bentuk(data))

    temuan, tak_dinilai, dinilai = [], [], 0
    for id_kt, id_trx, st_trx in batal:
        st_trx = getattr(st_trx, "value", st_trx)
        label = f"tindakan #{id_kt} (trx #{id_trx})"
        if st_trx != "BAYAR":
            tak_dinilai.append(f"{label} — transaksinya {st_trx} (data sebelum pagar T4-4)")
            continue
        dinilai += 1
        a, n_hak, n_ref = jadi_hak.get(id_kt, []), hak.get(id_kt, 0), refund.get(id_kt, 0)
        if len(a) > 1:
            temuan.append(f"{label}: disimpan sebagai hak {len(a)} kali")
            continue
        if n_ref > 1:
            temuan.append(f"{label}: {n_ref} refund — uang dikembalikan lebih dari sekali")
        if not a:
            if n_hak:
                temuan.append(f"{label}: ada hak PRABAYAR tanpa audit TINDAKAN_JADI_HAK")
            elif n_ref == 0:
                temuan.append(f"{label}: BATAL sesudah dibayar TANPA pasangan — bukan hak, "
                              f"tidak direfund (uangnya tak terjelaskan)")
            continue
        bentuk = a[0]
        if bentuk == "HAK" and n_hak != 1:
            temuan.append(f"{label}: bentuk HAK tapi rencana PRABAYAR = {n_hak} (harus 1)")
        elif bentuk in ("KUOTA", "SESI") and n_hak:
            temuan.append(f"{label}: bentuk {bentuk} tapi punya rencana PRABAYAR (hak ganda)")
        elif bentuk not in ("HAK", "KUOTA", "SESI"):
            temuan.append(f"{label}: audit TINDAKAN_JADI_HAK tanpa bentuk yang dikenal ({bentuk!r})")
        if bentuk == "KUOTA" and n_ref:
            temuan.append(f"{label}: kuota (Rp 0) dikembalikan DAN direfund")

    # Arah balik: setiap refund TINDAKAN / hak PRABAYAR menunjuk tindakan BATAL yang dibayar
    # transaksi refund itu.
    rq = (select(TransaksiRefund.id_refund, TransaksiRefund.id_transaksi,
                 TransaksiRefund.id_kunjungan_tindakan, KunjunganTindakan.status_tindakan,
                 KunjunganTindakan.id_transaksi)
          .join(KunjunganTindakan, KunjunganTindakan.id_kunjungan_tindakan
                == TransaksiRefund.id_kunjungan_tindakan)
          .where(*_filter(TransaksiRefund.id_kunjungan_tindakan)))
    for id_ref, trx_ref, id_kt, st_kt, trx_kt in db.execute(rq).all():
        st_kt = getattr(st_kt, "value", st_kt)
        if st_kt != "BATAL" or trx_kt != trx_ref:
            temuan.append(f"refund #{id_ref}: menunjuk tindakan #{id_kt} berstatus {st_kt}, "
                          f"transaksi tindakan #{trx_kt} ≠ transaksi refund #{trx_ref}")
    hq = (select(PasienRencanaTreatment.id_rencana, PasienRencanaTreatment.id_referensi_sumber,
                 KunjunganTindakan.status_tindakan, KunjunganTindakan.id_transaksi)
          .outerjoin(KunjunganTindakan, KunjunganTindakan.id_kunjungan_tindakan
                     == PasienRencanaTreatment.id_referensi_sumber)
          .where(PasienRencanaTreatment.sumber_rencana == SumberRencanaEnum.PRABAYAR)
          .where(*_filter(PasienRencanaTreatment.id_referensi_sumber)))
    for id_r, id_kt, st_kt, trx_kt in db.execute(hq).all():
        st_kt = getattr(st_kt, "value", st_kt)
        if st_kt != "BATAL" or trx_kt is None:
            temuan.append(f"hak #{id_r}: tindakan asal #{id_kt} berstatus {st_kt} / "
                          f"transaksi {trx_kt} — hak tanpa pembayaran")
    return {"temuan": temuan, "tak_dinilai": tak_dinilai, "dinilai": dinilai}


def main() -> int:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        h = periksa(db)
    finally:
        db.rollback()
        db.close()
    print("CEK TINDAKAN LUNAS-BATAL (bayar dulu tahap 4) — hanya membaca")
    print(f"  {h['dinilai']} tindakan BATAL sesudah dibayar dinilai")
    for t in h["tak_dinilai"]:
        print(f"  [tak dinilai] {t}")
    for t in h["temuan"]:
        print(f"  [TEMUAN] {t}")
    print(f"HASIL: {len(h['temuan'])} temuan")
    return 1 if h["temuan"] else 0


if __name__ == "__main__":
    sys.exit(main())
