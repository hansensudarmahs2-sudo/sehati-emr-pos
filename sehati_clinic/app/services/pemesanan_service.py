"""
PemesananService — orchestrator untuk modul Pengadaan.

State machine PO:
    SUBMITTED ─┬─→ ORDERED ─┬─→ PARTIAL_RECEIVED ─→ RECEIVED
               │            │
               └─→ CANCELLED └─→ CANCELLED

Key behaviors:
- create_pemesanan: validasi role per tipe item, snapshot nama/satuan, atomic insert
- update_header: HANYA saat status SUBMITTED
- approve_to_ordered: SUBMITTED→ORDERED, capture approver
- cancel: SUBMITTED→CANCELLED (oleh PURCHASING_FULL), atau ORDERED→CANCELLED (oleh Owner/Superadmin)
- receive_item: atomic — append receive event + update qty_diterima + update stok
                + inventory_history + smart-check status transition

Audit aksi:
- PO_CREATE, PO_UPDATE_HEADER, PO_APPROVE_ORDERED, PO_CANCEL, PO_RECEIVE_ITEM
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional


def _to_json_safe(value: Any) -> Any:
    """Serialize date/datetime/Decimal ke string supaya JSON-safe untuk audit_log."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import (
    InventoryStok,
    JenisMutasiEnum,
    KlinikApoteker,
    LokasiPengiriman,
    MasterProduk,
    MasterStaf,
    Pemesanan,
    PemesananItem,
    StafRoleEnum,
    StatusPemesananEnum,
)
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.pemesanan_repo import PemesananRepository
from app.repositories.master_produk_repo import MasterProdukRepository
from app.schemas.pengadaan import (
    PemesananCreateRequest,
    PemesananHeaderUpdate,
    ReceiveItemRequest,
)
from app.services.audit_service import AuditService


# State machine valid transitions
_VALID_TRANSITIONS = {
    StatusPemesananEnum.SUBMITTED: {StatusPemesananEnum.ORDERED, StatusPemesananEnum.CANCELLED},
    StatusPemesananEnum.ORDERED: {
        StatusPemesananEnum.PARTIAL_RECEIVED,
        StatusPemesananEnum.RECEIVED,
        StatusPemesananEnum.CANCELLED,
    },
    StatusPemesananEnum.PARTIAL_RECEIVED: {
        StatusPemesananEnum.PARTIAL_RECEIVED,  # idempotent
        StatusPemesananEnum.RECEIVED,
        StatusPemesananEnum.CANCELLED,         # tutup PO partial (sisa tak dikirim; yg diterima tetap)
    },
    StatusPemesananEnum.RECEIVED: set(),  # terminal
    StatusPemesananEnum.CANCELLED: set(),  # terminal
}

# Role yang boleh purchase BAHAN
_BAHAN_ROLES = {
    StafRoleEnum.OWNER,
    StafRoleEnum.SUPERADMIN,
    StafRoleEnum.PURCHASING,
}

# Role yang boleh purchase produk tipe CABIN/ALAT
_PRODUK_NON_RETAIL_ROLES = _BAHAN_ROLES


class PemesananService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PemesananRepository(db)
        self.produk_repo = MasterProdukRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.audit = AuditService(db)

    # =========================================================================
    # CREATE PO
    # =========================================================================
    def create_pemesanan(
        self,
        payload: PemesananCreateRequest,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> Pemesanan:
        """
        Atomic: validasi role + master items + snapshot, lalu insert header + items.

        Role validation per item:
        - Apoteker: hanya boleh tipe_item=PRODUK dengan master_produk.tipe_produk=RETAIL
        - Lainnya (Owner/Superadmin/Purchasing): semua tipe OK
        """
        # ----- 1. Resolve role string -----
        actor_role = actor.role if isinstance(actor.role, StafRoleEnum) else StafRoleEnum(actor.role)

        # ----- 2. Validate + snapshot items -----
        item_models: list[PemesananItem] = []
        total_estimasi = 0.0

        for idx, it in enumerate(payload.items):
            # Resolve tipe_item value
            tipe_value = it.tipe_item.value if hasattr(it.tipe_item, "value") else str(it.tipe_item)

            if tipe_value == "PRODUK":
                if it.id_produk is None:
                    raise HTTPException(400, f"Item #{idx+1}: id_produk wajib untuk tipe PRODUK.")
                produk = self.produk_repo.get_by_id(it.id_produk)
                if produk is None:
                    raise HTTPException(404, f"Item #{idx+1}: Produk id={it.id_produk} tidak ditemukan.")
                # Role check
                tipe_produk = (produk.tipe_produk.value if hasattr(produk.tipe_produk, "value")
                               else str(produk.tipe_produk))
                if actor_role == StafRoleEnum.APOTEKER and tipe_produk != "RETAIL":
                    raise HTTPException(
                        403,
                        f"Item #{idx+1}: Apoteker hanya boleh PO produk tipe RETAIL, "
                        f"bukan {tipe_produk}.",
                    )
                # Snapshot — untuk PO, sertakan merk asli (nama_dagang) supaya
                # bagian pembelian tahu barang yang dimaksud (kode sediaan saja tidak cukup).
                nama_snap = produk.nama_produk
                if getattr(produk, "nama_dagang", None):
                    nama_snap = f"{produk.nama_produk} — {produk.nama_dagang}"[:100]
                satuan_snap = produk.satuan
            elif tipe_value == "BAHAN":
                if it.id_bahan is None:
                    raise HTTPException(400, f"Item #{idx+1}: id_bahan wajib untuk tipe BAHAN.")
                # Role check — APOTEKER tidak boleh BAHAN
                if actor_role not in _BAHAN_ROLES:
                    raise HTTPException(
                        403,
                        f"Item #{idx+1}: Role {actor_role.value} tidak boleh PO bahan klinik. "
                        "Hanya Owner/Superadmin/Purchasing.",
                    )
                bahan = self.inv_repo.get_stok(it.id_bahan)
                if bahan is None:
                    raise HTTPException(404, f"Item #{idx+1}: Bahan id={it.id_bahan} tidak ditemukan.")
                nama_snap = bahan.nama_bahan
                satuan_snap = bahan.satuan_pembelian or bahan.satuan
            else:
                raise HTTPException(400, f"Item #{idx+1}: tipe_item '{tipe_value}' invalid.")

            # Subtotal compute (opsional)
            subtotal = None
            if it.harga_satuan is not None:
                subtotal = float(it.harga_satuan) * float(it.qty_dipesan)
                total_estimasi += subtotal

            item_models.append(PemesananItem(
                tipe_item=tipe_value,
                id_produk=it.id_produk if tipe_value == "PRODUK" else None,
                id_bahan=it.id_bahan if tipe_value == "BAHAN" else None,
                nama_snapshot=nama_snap,
                satuan_snapshot=satuan_snap,
                qty_dipesan=float(it.qty_dipesan),
                qty_diterima=0,
                harga_satuan=it.harga_satuan,
                subtotal=subtotal,
                catatan_item=it.catatan_item,
            ))

        # ----- 2b. Apoteker penanggung jawab (WAJIB) + snapshot -----
        if payload.id_apoteker is None:
            raise HTTPException(400, "Apoteker penanggung jawab wajib dipilih.")
        apoteker = self.db.get(KlinikApoteker, payload.id_apoteker)
        if apoteker is None or not apoteker.is_active:
            raise HTTPException(400, "Apoteker tidak ditemukan atau tidak aktif.")

        # SHIP-L3: ship-to (opsional) — snapshot nama+alamat
        kirim_nama = None
        kirim_alamat = None
        if payload.id_lokasi_pengiriman is not None:
            lok = self.db.get(LokasiPengiriman, payload.id_lokasi_pengiriman)
            if lok is not None:
                kirim_nama = lok.nama
                kirim_alamat = lok.alamat

        # ----- 3. Generate nomor PO + create header -----
        nomor_po = self.repo.generate_next_nomor_po()
        pemesanan = Pemesanan(
            nomor_po=nomor_po,
            tgl_pemesanan=datetime.now(),
            tgl_perkiraan_datang=payload.tgl_perkiraan_datang,
            supplier_nama=payload.supplier_nama,
            status=StatusPemesananEnum.SUBMITTED,
            id_staf_pemesan=actor.id_staf,
            catatan=payload.catatan,
            total_estimasi_biaya=(total_estimasi if total_estimasi > 0 else None),
            termin_hari=payload.termin_hari,
            validitas_hari=payload.validitas_hari,
            id_apoteker=apoteker.id_apoteker,
            apoteker_nama=apoteker.nama_apoteker,
            apoteker_sipa=apoteker.no_sipa,
            id_lokasi_pengiriman=payload.id_lokasi_pengiriman,
            kirim_ke_nama=kirim_nama,
            kirim_ke_alamat=kirim_alamat,
        )

        try:
            self.repo.create_with_items(pemesanan, item_models)

            self.audit.log_create(
                id_staf=actor.id_staf,
                tabel="pemesanan",
                id_target=pemesanan.id_pemesanan,
                data_baru={
                    "nomor_po": pemesanan.nomor_po,
                    "supplier_nama": pemesanan.supplier_nama,
                    "status": pemesanan.status.value,
                    "jumlah_item": len(item_models),
                    "total_estimasi_biaya": float(total_estimasi) if total_estimasi else None,
                },
                request=request,
            )
            self.db.commit()
            self.db.refresh(pemesanan)
            return pemesanan
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal create PO: {e!s}")

    # =========================================================================
    # UPDATE HEADER (SUBMITTED only)
    # =========================================================================
    def update_header(
        self,
        id_pemesanan: int,
        payload: PemesananHeaderUpdate,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> Pemesanan:
        pemesanan = self.repo.get_by_id(id_pemesanan)
        if pemesanan is None:
            raise HTTPException(404, f"PO {id_pemesanan} tidak ditemukan.")
        if pemesanan.status != StatusPemesananEnum.SUBMITTED:
            raise HTTPException(
                400,
                f"PO {pemesanan.nomor_po} sudah {pemesanan.status.value}, "
                "tidak bisa diedit. Hanya SUBMITTED yang bisa diedit.",
            )
        update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return pemesanan
        try:
            # Snapshot data_lama + serialize date/datetime ke ISO string supaya JSON-safe
            data_lama_raw = {k: getattr(pemesanan, k, None) for k in update_data.keys()}
            data_lama = {k: _to_json_safe(v) for k, v in data_lama_raw.items()}
            data_baru = {k: _to_json_safe(v) for k, v in update_data.items()}
            self.repo.update_header(pemesanan, update_data)
            self.audit.log_update(
                id_staf=actor.id_staf,
                tabel="pemesanan",
                id_target=pemesanan.id_pemesanan,
                data_lama=data_lama,
                data_baru=data_baru,
                request=request,
            )
            self.db.commit()
            self.db.refresh(pemesanan)
            return pemesanan
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal update PO: {e!s}")

    # =========================================================================
    # APPROVE → ORDERED
    # =========================================================================
    def approve_to_ordered(
        self,
        id_pemesanan: int,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> Pemesanan:
        pemesanan = self.repo.get_by_id(id_pemesanan)
        if pemesanan is None:
            raise HTTPException(404, f"PO {id_pemesanan} tidak ditemukan.")
        self._check_transition(pemesanan.status, StatusPemesananEnum.ORDERED)
        try:
            status_lama = pemesanan.status.value
            self.repo.update_status(pemesanan, StatusPemesananEnum.ORDERED, actor.id_staf)
            self.audit.log(
                aksi="PO_APPROVE_ORDERED",
                id_staf=actor.id_staf,
                tabel_target="pemesanan",
                id_target=pemesanan.id_pemesanan,
                data_lama={"status": status_lama},
                data_baru={"status": "ORDERED", "id_staf_approver": actor.id_staf},
                keterangan=f"PO {pemesanan.nomor_po} di-approve ke ORDERED.",
                request=request,
            )
            self.db.commit()
            self.db.refresh(pemesanan)
            return pemesanan
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal approve PO: {e!s}")

    # =========================================================================
    # CANCEL
    # =========================================================================
    def cancel(
        self,
        id_pemesanan: int,
        actor: MasterStaf,
        alasan: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> Pemesanan:
        pemesanan = self.repo.get_by_id(id_pemesanan)
        if pemesanan is None:
            raise HTTPException(404, f"PO {id_pemesanan} tidak ditemukan.")
        self._check_transition(pemesanan.status, StatusPemesananEnum.CANCELLED)
        try:
            status_lama = pemesanan.status.value
            self.repo.update_status(pemesanan, StatusPemesananEnum.CANCELLED)
            self.audit.log(
                aksi="PO_CANCEL",
                id_staf=actor.id_staf,
                tabel_target="pemesanan",
                id_target=pemesanan.id_pemesanan,
                data_lama={"status": status_lama},
                data_baru={"status": "CANCELLED"},
                keterangan=f"PO {pemesanan.nomor_po} cancelled. Alasan: {alasan or '-'}",
                request=request,
            )
            self.db.commit()
            self.db.refresh(pemesanan)
            return pemesanan
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal cancel PO: {e!s}")

    # =========================================================================
    # RECEIVE ITEM — atomic + audit + state transition
    # =========================================================================
    def receive_item(
        self,
        id_pemesanan: int,
        payload: ReceiveItemRequest,
        actor: MasterStaf,
        request: Optional[Request] = None,
    ) -> dict:
        """
        Atomic receive event:
        1. Validate PO status (ORDERED atau PARTIAL_RECEIVED)
        2. Lock item FOR UPDATE
        3. Validate qty (tidak boleh > sisa)
        4. Lock target stok (master_produk atau inventory_stok) FOR UPDATE
        5. Insert pemesanan_receive event
        6. Update qty_diterima di item
        7. Update stok (master_produk.stok_terkini ATAU inventory_stok.stok_gudang_utama)
        8. Insert inventory_history dengan referensi PO + faktur
        9. Smart-check: kalau semua item complete → status PO RECEIVED, sebagian → PARTIAL_RECEIVED
        10. Audit log
        """
        pemesanan = self.repo.get_by_id(id_pemesanan)
        if pemesanan is None:
            raise HTTPException(404, f"PO {id_pemesanan} tidak ditemukan.")
        if pemesanan.status not in (StatusPemesananEnum.ORDERED, StatusPemesananEnum.PARTIAL_RECEIVED):
            raise HTTPException(
                400,
                f"PO status {pemesanan.status.value} — receive hanya valid untuk "
                "ORDERED atau PARTIAL_RECEIVED.",
            )

        # ----- 2. Lock item -----
        item = self.repo.get_item_for_update(payload.id_pemesanan_item)
        if item is None or item.id_pemesanan != id_pemesanan:
            raise HTTPException(404, f"Item {payload.id_pemesanan_item} tidak ditemukan di PO ini.")

        sisa = float(item.qty_dipesan) - float(item.qty_diterima or 0)
        if payload.qty_diterima > sisa:
            raise HTTPException(
                400,
                f"Qty receive ({payload.qty_diterima}) melebihi sisa ({sisa}) untuk item "
                f"'{item.nama_snapshot}'. qty_dipesan={item.qty_dipesan}, "
                f"qty_diterima sebelumnya={item.qty_diterima}.",
            )

        # ----- 3. Role check untuk tipe item -----
        actor_role = actor.role if isinstance(actor.role, StafRoleEnum) else StafRoleEnum(actor.role)
        if item.tipe_item == "BAHAN" and actor_role not in _BAHAN_ROLES:
            raise HTTPException(
                403,
                f"Role {actor_role.value} tidak boleh receive bahan klinik. "
                "Hanya Owner/Superadmin/Purchasing.",
            )

        try:
            # ----- 4. Lock + update stok target -----
            stok_sebelum = 0.0
            stok_sesudah = 0.0
            history_target_id_bahan = None
            history_target_id_produk = None
            history_tipe_item = item.tipe_item

            if item.tipe_item == "PRODUK":
                produk = self.repo.get_produk_for_update(item.id_produk)
                if produk is None:
                    raise HTTPException(404, f"Produk id={item.id_produk} tidak ditemukan.")
                # Role check untuk produk CABIN/ALAT
                tipe_produk = (produk.tipe_produk.value if hasattr(produk.tipe_produk, "value")
                               else str(produk.tipe_produk))
                if actor_role == StafRoleEnum.APOTEKER and tipe_produk != "RETAIL":
                    raise HTTPException(
                        403,
                        f"Apoteker hanya boleh receive produk RETAIL, bukan {tipe_produk}.",
                    )
                stok_sebelum = float(produk.stok_terkini or 0)
                produk.stok_terkini = stok_sebelum + float(payload.qty_diterima)
                stok_sesudah = produk.stok_terkini
                self.db.flush()
                history_target_id_produk = produk.id_produk
            else:  # BAHAN
                bahan = self.repo.get_bahan_for_update(item.id_bahan)
                if bahan is None:
                    raise HTTPException(404, f"Bahan id={item.id_bahan} tidak ditemukan.")
                stok_sebelum = float(bahan.stok_gudang_utama or 0)
                bahan.stok_gudang_utama = stok_sebelum + float(payload.qty_diterima)
                stok_sesudah = bahan.stok_gudang_utama
                self.db.flush()
                history_target_id_bahan = bahan.id_bahan

            # ----- 5. Insert pemesanan_receive event -----
            receive_event = self.repo.add_receive_event(
                id_pemesanan=id_pemesanan,
                id_pemesanan_item=item.id_item,
                qty_diterima=float(payload.qty_diterima),
                id_staf_penerima=actor.id_staf,
                nomor_faktur=payload.nomor_faktur,
                catatan=payload.catatan,
                batch_no=getattr(payload, "batch_no", None),
                tgl_ed=getattr(payload, "tgl_ed", None),
                harga_terima=getattr(payload, "harga_terima", None),
                id_distributor=getattr(payload, "id_distributor", None),
                id_faktur=getattr(payload, "id_faktur", None),
            )

            # ----- 5b. Buat STOK_LOT (P-L4/DEC-090) untuk qty yang diterima -----
            from datetime import date as _date
            from app.db.models import StokLot
            lot = StokLot(
                tipe_item=item.tipe_item,
                id_produk=(item.id_produk if item.tipe_item == "PRODUK" else None),
                id_bahan=(item.id_bahan if item.tipe_item == "BAHAN" else None),
                lokasi=("RETAIL" if item.tipe_item == "PRODUK" else "GUDANG_UTAMA"),
                batch_no=getattr(payload, "batch_no", None),
                tgl_ed=getattr(payload, "tgl_ed", None),
                qty_masuk=float(payload.qty_diterima),
                qty_sisa=float(payload.qty_diterima),
                harga_terima=getattr(payload, "harga_terima", None),
                id_receive=receive_event.id_receive,
                id_distributor=getattr(payload, "id_distributor", None),
                tgl_masuk=_date.today(),
                status="AKTIF",
            )
            self.db.add(lot)
            self.db.flush()

            # ----- 6. Update qty_diterima di item -----
            qty_total = self.repo.update_item_qty_diterima(item, float(payload.qty_diterima))

            # ----- 7. Insert inventory_history -----
            self.inv_repo.add_history(
                tipe_item=history_tipe_item,
                id_bahan=history_target_id_bahan,
                id_produk=history_target_id_produk,
                id_staf=actor.id_staf,
                jenis=JenisMutasiEnum.RESTOCK,
                qty_perubahan=float(payload.qty_diterima),
                stok_akhir=stok_sesudah,
                referensi=pemesanan.nomor_po,
                keterangan=(
                    f"Receive PO {pemesanan.nomor_po} item '{item.nama_snapshot}' "
                    f"qty {payload.qty_diterima}"
                    + (f", faktur {payload.nomor_faktur}" if payload.nomor_faktur else "")
                ),
            )

            # ----- 8. Smart-check status PO transition -----
            item_complete = (qty_total >= float(item.qty_dipesan))
            all_items = self.repo.get_items_by_po(id_pemesanan)
            all_complete = all(
                float(i.qty_diterima or 0) >= float(i.qty_dipesan) for i in all_items
            )
            status_lama_value = pemesanan.status.value
            if all_complete:
                self.repo.update_status(pemesanan, StatusPemesananEnum.RECEIVED)
                status_baru = "RECEIVED"
            else:
                if pemesanan.status == StatusPemesananEnum.ORDERED:
                    self.repo.update_status(pemesanan, StatusPemesananEnum.PARTIAL_RECEIVED)
                status_baru = "PARTIAL_RECEIVED"

            # ----- 9. Audit log -----
            self.audit.log(
                aksi="PO_RECEIVE_ITEM",
                id_staf=actor.id_staf,
                tabel_target="pemesanan_receive",
                id_target=receive_event.id_receive,
                data_baru={
                    "id_pemesanan": id_pemesanan,
                    "nomor_po": pemesanan.nomor_po,
                    "id_item": item.id_item,
                    "nama_item": item.nama_snapshot,
                    "tipe_item": item.tipe_item,
                    "qty_diterima_event": payload.qty_diterima,
                    "qty_diterima_total": qty_total,
                    "qty_dipesan": item.qty_dipesan,
                    "stok_sebelum": stok_sebelum,
                    "stok_sesudah": stok_sesudah,
                    "nomor_faktur": payload.nomor_faktur,
                    "status_po_baru": status_baru,
                },
                keterangan=(
                    f"Receive {payload.qty_diterima} {item.satuan_snapshot or 'unit'} "
                    f"'{item.nama_snapshot}' di PO {pemesanan.nomor_po}."
                ),
                request=request,
            )

            self.db.commit()
            return {
                "status": "success",
                "message": (
                    f"Receive berhasil. Item '{item.nama_snapshot}' "
                    f"({qty_total}/{item.qty_dipesan}). "
                    f"Status PO: {status_baru}."
                ),
                "data": {
                    "id_receive": receive_event.id_receive,
                    "id_pemesanan": id_pemesanan,
                    "id_pemesanan_item": item.id_item,
                    "qty_diterima_event": float(payload.qty_diterima),
                    "qty_diterima_total": qty_total,
                    "qty_dipesan": float(item.qty_dipesan),
                    "item_complete": item_complete,
                    "stok_sebelum": stok_sebelum,
                    "stok_sesudah": stok_sesudah,
                    "status_pemesanan_baru": status_baru,
                },
            }
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(500, f"Gagal receive item: {e!s}")

    # =========================================================================
    # State machine guard
    # =========================================================================
    def _check_transition(
        self,
        current: StatusPemesananEnum,
        target: StatusPemesananEnum,
    ) -> None:
        valid = _VALID_TRANSITIONS.get(current, set())
        if target not in valid:
            raise HTTPException(
                400,
                f"Transition {current.value} → {target.value} tidak valid.",
            )


__all__ = ["PemesananService"]
