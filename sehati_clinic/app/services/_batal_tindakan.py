"""Mengembalikan yang dipakai tindakan yang DIBATALKAN sebelum dikerjakan & dibayar — SATU tempat.

Dua pemanggil, satu aturan (CLAUDE.md §4.1 "satu hal, dua penulis"):
  1. `KunjunganService._bereskan_batal` — seluruh kunjungan dibatalkan FO (Audit T2-5/T2-6).
  2. `TreatmentService.batalkan_tindakan` — satu tindakan PENDING ditolak pasien (Ruling 12,
     bayar dulu; spec DESAIN_BAYAR_DULU_BERCABANG.md §3.6 cabang "belum dibayar").

Yang dikembalikan:
  - kuota membership tindakan ber-`id_kuota_member` (dipakai saat SOAP/upsell disimpan);
  - sesi series yang DIJADWALKAN ke tindakan itu (SCHEDULED) → PENDING, bisa dipakai lagi;
  - series yang LAHIR di kunjungan itu dan sesi 1-nya belum dibayar → CANCELLED: sesi 1
    membawa harga paket, jadi sesi 2..N tak boleh tersisa untuk dipakai gratis (T2-6).

⚠ Tindakan yang SUDAH `BATAL` tidak pernah dikembalikan lagi. Tanpa saringan itu, Batalkan
tindakan lalu Batal kunjungan mengembalikan kuota yang sama DUA kali (pasien mendapat slot
gratis). Sama halnya void: lingkup void tindakan = `id_transaksi` (Ruling 13), dan tindakan
BATAL-belum-dibayar tidak pernah ber-`id_transaksi`.

Semua FLUSH saja; pemanggil yang commit — gagal satu, batal semua.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KunjunganTindakan, PasienRencanaTreatment, StatusRencanaTreatmentEnum
from app.db.models._enums import StatusTindakanEnum

_AKTIF = (StatusRencanaTreatmentEnum.PENDING, StatusRencanaTreatmentEnum.SCHEDULED)


def kembalikan_kuota(db: Session, tindakan_list, *, actor_id_staf, id_kunjungan, request) -> int:
    """`decrement_kuota_terpakai` untuk tiap tindakan ber-kuota yang belum BATAL."""
    from app.services.membership_service import MembershipService
    ms = MembershipService(db)
    n = 0
    for t in tindakan_list:
        if t.id_kuota_member is None or t.status_tindakan == StatusTindakanEnum.BATAL:
            continue
        if ms.decrement_kuota_terpakai(t.id_kuota_member, actor_id_staf=actor_id_staf,
                                       id_kunjungan=id_kunjungan,
                                       id_tindakan=t.id_kunjungan_tindakan, request=request):
            n += 1
    return n


def batalkan_series(db: Session, audit, rencana_list, *, trigger, actor_id_staf, request) -> int:
    """Rencana aktif → CANCELLED (audit BATAL_SERIES_CANCEL)."""
    n = 0
    for r in rencana_list:
        if r.status not in _AKTIF:
            continue
        r.status = StatusRencanaTreatmentEnum.CANCELLED
        audit.log(aksi="BATAL_SERIES_CANCEL", id_staf=actor_id_staf or 0,
                  tabel_target="pasien_rencana_treatment", id_target=r.id_rencana,
                  data_baru={"status": "CANCELLED", "trigger": trigger}, request=request)
        n += 1
    return n


def kembalikan_sesi(db: Session, audit, rencana_list, *, trigger, actor_id_staf, request) -> int:
    """Sesi SCHEDULED → PENDING (audit BATAL_SERIES_KEMBALI). Penanda eksekusi dikosongkan
    supaya sesi tak tampak pernah dikerjakan di kunjungan yang dibatalkan."""
    n = 0
    for r in rencana_list:
        if r.status != StatusRencanaTreatmentEnum.SCHEDULED:
            continue
        r.status = StatusRencanaTreatmentEnum.PENDING
        r.id_kunjungan_eksekusi = None
        r.tgl_eksekusi = None
        audit.log(aksi="BATAL_SERIES_KEMBALI", id_staf=actor_id_staf or 0,
                  tabel_target="pasien_rencana_treatment", id_target=r.id_rencana,
                  data_lama={"status": "SCHEDULED"},
                  data_baru={"status": "PENDING", "trigger": trigger}, request=request)
        n += 1
    return n


def bereskan_satu_tindakan(db: Session, audit, tindakan, *, actor_id_staf, request) -> dict:
    """Kembalikan pemakaian SATU tindakan PENDING belum dibayar (dipanggil SEBELUM status
    tindakan ditulis BATAL — `kembalikan_kuota` melewati yang sudah BATAL)."""
    from app.services._series import anggota
    trigger = f"batal_tindakan_{tindakan.id_kunjungan_tindakan}"
    hasil = {"kuota": kembalikan_kuota(db, [tindakan], actor_id_staf=actor_id_staf,
                                       id_kunjungan=tindakan.id_kunjungan, request=request),
             "series_cancel": 0, "sesi_kembali": 0}
    if tindakan.id_rencana:
        r = db.get(PasienRencanaTreatment, tindakan.id_rencana)
        if r is not None:
            # Sesi 1 series yang LAHIR di kunjungan ini (tindakan ini belum dibayar — dicek
            # pemanggil) → seluruh series ini; selain itu sesi yang dijadwalkan → PENDING.
            if r.id_kunjungan_pembuat == tindakan.id_kunjungan and (r.urutan_sesi or 1) <= 1:
                hasil["series_cancel"] = batalkan_series(
                    db, audit, anggota(db, r), trigger=trigger,
                    actor_id_staf=actor_id_staf, request=request)
            else:
                hasil["sesi_kembali"] = kembalikan_sesi(
                    db, audit, [r], trigger=trigger, actor_id_staf=actor_id_staf, request=request)
    db.flush()
    return hasil


def bereskan_kunjungan(db: Session, audit, id_kunjungan, *, actor_id_staf, request) -> None:
    """Versi seluruh kunjungan (`KunjunganService._bereskan_batal`, T2-5/T2-6): semua series
    yang lahir di sini dibatalkan (belum ada pembayaran — pagar BATAL), sesi yang dijadwalkan
    ke kunjungan ini kembali PENDING."""
    k = id_kunjungan
    trigger = f"batal_kunjungan_{k}"
    kembalikan_kuota(db, db.execute(select(KunjunganTindakan).where(
        KunjunganTindakan.id_kunjungan == k,
        KunjunganTindakan.id_kuota_member.is_not(None))).scalars().all(),
        actor_id_staf=actor_id_staf, id_kunjungan=k, request=request)
    lahir = db.execute(select(PasienRencanaTreatment).where(
        PasienRencanaTreatment.id_kunjungan_pembuat == k,
        PasienRencanaTreatment.status.in_(_AKTIF))).scalars().all()
    batalkan_series(db, audit, lahir, trigger=trigger, actor_id_staf=actor_id_staf, request=request)
    id_lahir = {r.id_rencana for r in lahir}
    dijadwalkan = [r for r in db.execute(
        select(PasienRencanaTreatment)
        .join(KunjunganTindakan, KunjunganTindakan.id_rencana == PasienRencanaTreatment.id_rencana)
        .where(KunjunganTindakan.id_kunjungan == k)
        .where(PasienRencanaTreatment.status == StatusRencanaTreatmentEnum.SCHEDULED)
    ).scalars().all() if r.id_rencana not in id_lahir]
    kembalikan_sesi(db, audit, dijadwalkan, trigger=trigger, actor_id_staf=actor_id_staf,
                    request=request)
    db.flush()
