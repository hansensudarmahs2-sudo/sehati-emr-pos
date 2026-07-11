"""
KlinikConfigService — singleton config klinik untuk Print Module.

Operations:
- get_config()                  : Fetch row id_config=1 (auto-create kalau hilang).
- update_with_audit(...)        : Update fields + audit log (service-owned txn).
- save_logo(file_bytes, ext)    : Validate + save logo file ke static/uploads/.
- delete_logo()                 : Remove logo_path + delete file dari disk.

Validation:
- Logo: max 500KB, PNG atau JPG only (cek magic bytes).
- default_paper_*: harus 'a5' atau 'thermal'.

DEC-047: Print Module Path A — Browser HTML print, no PDF library.
DEC-030: Service-owned transaction (commit di sini, bukan di route).
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KlinikApoteker, MasterKlinikConfig
from app.services.audit_service import AuditService


LOGO_MAX_BYTES = 500 * 1024  # 500 KB
LOGO_ALLOWED_EXTS = {"png", "jpg", "jpeg"}
VALID_PAPER_SIZES = {"a5", "thermal"}

# Magic bytes signature untuk validasi file type
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_JPG = b"\xff\xd8\xff"


class KlinikConfigService:

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # GET — auto-create singleton kalau row hilang
    # =========================================================================
    def get_config(self) -> MasterKlinikConfig:
        """
        Return row id_config=1. Auto-create kalau hilang (defensive).

        Migration 007 sudah INSERT default row, jadi normalnya row 1 selalu ada.
        Auto-create di sini sebagai safety net.
        """
        row = self.db.execute(
            select(MasterKlinikConfig).where(MasterKlinikConfig.id_config == 1)
        ).scalars().first()

        if row is None:
            # Defensive — create default singleton row
            row = MasterKlinikConfig(
                id_config=1,
                nama_klinik="Klinik Anda",
                default_paper_nota="a5",
                default_paper_soap="a5",
                footer_text="Terima kasih atas kunjungan Bapak/Ibu. Semoga lekas sembuh.",
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)

        return row

    # =========================================================================
    # UPDATE — semua field text + paper size, plus audit
    # =========================================================================
    def update_with_audit(
        self,
        update_data: dict,
        actor_id_staf: int,
        request: Optional[Request] = None,
    ) -> MasterKlinikConfig:
        """
        Update master_klinik_config dengan field-field di update_data dict.

        Allowed fields:
            nama_klinik, alamat_baris1, alamat_baris2, alamat_baris3,
            no_telepon, no_whatsapp, email, website, footer_text,
            default_paper_nota, default_paper_soap, ttd_dokter_text, logo_path.

        Validation:
            - default_paper_* harus 'a5' atau 'thermal'.
            - nama_klinik tidak boleh empty.

        Audit log: aksi=UPDATE, tabel_target=master_klinik_config.
        """
        if not update_data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "update_data kosong")

        allowed_fields = {
            "nama_klinik", "alamat_baris1", "alamat_baris2", "alamat_baris3",
            "no_telepon", "no_whatsapp", "email", "website",
            "footer_text", "default_paper_nota", "default_paper_soap",
            "ttd_dokter_text", "logo_path", "mini_logo_path",
            # MK-L2: identitas untuk PO / RM
            "no_sia", "rm_prefix", "kode_klinik",
            # DYN-L1: reorder point dinamis
            "lead_time_hari", "safety_hari",
        }

        clean_data = {k: v for k, v in update_data.items() if k in allowed_fields}
        if not clean_data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada field valid di update_data")

        # Validation
        if "nama_klinik" in clean_data:
            nama = (clean_data["nama_klinik"] or "").strip()
            if not nama:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "nama_klinik tidak boleh kosong")
            if len(nama) > 100:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "nama_klinik maksimum 100 karakter")
            clean_data["nama_klinik"] = nama

        if "rm_prefix" in clean_data:
            pref = (clean_data["rm_prefix"] or "").strip().upper()
            if len(pref) > 5:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "rm_prefix maksimum 5 karakter")
            clean_data["rm_prefix"] = pref or None
        if "kode_klinik" in clean_data:
            clean_data["kode_klinik"] = (clean_data["kode_klinik"] or "").strip().upper() or None
        if "no_sia" in clean_data:
            clean_data["no_sia"] = (clean_data["no_sia"] or "").strip() or None
        for _f in ("lead_time_hari", "safety_hari"):
            if _f in clean_data:
                try:
                    v = int(clean_data[_f])
                except (TypeError, ValueError):
                    v = 14 if _f == "lead_time_hari" else 7
                clean_data[_f] = max(0, min(v, 365))

        for paper_field in ("default_paper_nota", "default_paper_soap"):
            if paper_field in clean_data and clean_data[paper_field] not in VALID_PAPER_SIZES:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{paper_field} harus salah satu: {sorted(VALID_PAPER_SIZES)}",
                )

        row = self.get_config()
        data_lama = {f: getattr(row, f) for f in clean_data.keys()}

        try:
            for field, value in clean_data.items():
                setattr(row, field, value)
            row.id_staf_last_edit = actor_id_staf

            AuditService(self.db).log_update(
                id_staf=actor_id_staf,
                tabel="master_klinik_config",
                id_target=1,
                data_lama=data_lama,
                data_baru=clean_data,
                request=request,
            )
            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    # =========================================================================
    # APOTEKER (MK-L2) — daftar apoteker + SIPA per klinik (dropdown PO)
    # =========================================================================
    def list_apoteker(self, only_active: bool = False):
        """List apoteker klinik (default: semua; aktif dulu lalu nama)."""
        q = select(KlinikApoteker).where(KlinikApoteker.id_klinik == 1)
        if only_active:
            q = q.where(KlinikApoteker.is_active.is_(True))
        q = q.order_by(KlinikApoteker.is_active.desc(), KlinikApoteker.nama_apoteker)
        return self.db.execute(q).scalars().all()

    def add_apoteker(self, nama_apoteker: str, no_sipa: Optional[str],
                     masa_berlaku, actor_id_staf: int,
                     request: Optional[Request] = None) -> KlinikApoteker:
        nama = (nama_apoteker or "").strip()
        if not nama:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nama apoteker wajib diisi.")
        ap = KlinikApoteker(
            id_klinik=1, nama_apoteker=nama,
            no_sipa=(no_sipa or "").strip() or None,
            masa_berlaku=masa_berlaku, is_active=True,
        )
        try:
            self.db.add(ap)
            self.db.flush()
            AuditService(self.db).log_create(
                id_staf=actor_id_staf, tabel="klinik_apoteker", id_target=ap.id_apoteker,
                data_baru={"nama_apoteker": nama, "no_sipa": ap.no_sipa}, request=request,
            )
            self.db.commit()
            self.db.refresh(ap)
            return ap
        except Exception:
            self.db.rollback()
            raise

    def set_apoteker_active(self, id_apoteker: int, active: bool, actor_id_staf: int,
                            request: Optional[Request] = None) -> KlinikApoteker:
        ap = self.db.get(KlinikApoteker, id_apoteker)
        if ap is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Apoteker tidak ditemukan.")
        old = bool(ap.is_active)
        try:
            ap.is_active = active
            AuditService(self.db).log_update(
                id_staf=actor_id_staf, tabel="klinik_apoteker", id_target=id_apoteker,
                data_lama={"is_active": old}, data_baru={"is_active": active}, request=request,
            )
            self.db.commit()
            self.db.refresh(ap)
            return ap
        except Exception:
            self.db.rollback()
            raise

    # =========================================================================
    # LOGO — save file ke disk
    # =========================================================================
    def save_logo(
        self,
        file_bytes: bytes,
        original_filename: str,
        upload_dir: Optional[Path] = None,
        basename: str = "logo",
    ) -> str:
        """
        Validate + save logo file. Return relative path (e.g., 'uploads/logo.png').

        Args:
            file_bytes: raw bytes dari upload
            original_filename: nama file asli (untuk ambil extension)
            upload_dir: optional override (default: sehati_clinic/static/uploads/)

        Validation:
            - Size <= LOGO_MAX_BYTES (500 KB)
            - Extension harus png/jpg/jpeg
            - Magic bytes match (anti-spoofing)
        """
        if not file_bytes:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File kosong")

        if len(file_bytes) > LOGO_MAX_BYTES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"File terlalu besar (max {LOGO_MAX_BYTES // 1024} KB)",
            )

        # Determine extension
        ext = (original_filename.rsplit(".", 1)[-1] if "." in original_filename else "").lower()
        if ext not in LOGO_ALLOWED_EXTS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Extension harus salah satu: {sorted(LOGO_ALLOWED_EXTS)}",
            )

        # Magic bytes check
        if ext == "png" and not file_bytes.startswith(_MAGIC_PNG):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File tidak match format PNG")
        if ext in ("jpg", "jpeg") and not file_bytes.startswith(_MAGIC_JPG):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File tidak match format JPG")

        # Normalize extension untuk filename
        save_ext = "jpg" if ext == "jpeg" else ext

        # Resolve upload dir
        if upload_dir is None:
            here = Path(__file__).resolve().parent.parent.parent  # sehati_clinic/
            upload_dir = here / "static" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save (overwrite kalau ada — owner edit logo)
        filename = f"{basename}.{save_ext}"
        full_path = upload_dir / filename
        with open(full_path, "wb") as f:
            f.write(file_bytes)

        # Cleanup file basename yang sama dengan extension lain (e.g., dulu png sekarang jpg)
        for other_ext in LOGO_ALLOWED_EXTS:
            other_name = f"{basename}.jpg" if other_ext == "jpeg" else f"{basename}.{other_ext}"
            if other_name != filename:
                other_path = upload_dir / other_name
                if other_path.exists():
                    try:
                        other_path.unlink()
                    except OSError:
                        pass  # silent — tidak critical

        # Return relative path untuk disimpan di DB
        return f"uploads/{filename}"

    def delete_logo(
        self,
        actor_id_staf: int,
        request: Optional[Request] = None,
        field: str = "logo_path",
    ) -> None:
        """
        Hapus path logo (field= logo_path / mini_logo_path) dari config + delete file.
        Update + audit via update_with_audit.
        """
        row = self.get_config()
        current = getattr(row, field, None)
        if not current:
            return  # nothing to delete

        # Delete file dari disk (best-effort)
        here = Path(__file__).resolve().parent.parent.parent
        file_path = here / "static" / current
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass  # silent

        # Clear path di DB + audit
        self.update_with_audit(
            update_data={field: None},
            actor_id_staf=actor_id_staf,
            request=request,
        )


__all__ = ["KlinikConfigService", "VALID_PAPER_SIZES", "LOGO_MAX_BYTES"]
