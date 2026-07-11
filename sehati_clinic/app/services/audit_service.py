"""
AuditService — record semua aksi mutating sensitif.

Skeleton untuk Minggu 3 dst. Pattern: panggil `audit.log(...)` di service
sebelum/sesudah aksi penting (CREATE/UPDATE/DELETE/LOGIN/VOID/dll).

Best practices:
- Append-only. Tidak ada update/delete row audit_log.
- Panggil di service layer, BUKAN di repository.
- Snapshot data_lama & data_baru sebagai JSON.
- Pakai try/except — kalau audit log gagal, jangan block business logic.
"""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog, StatusAksiAuditEnum


logger = logging.getLogger(__name__)


class AuditService:
    """Logger untuk semua aksi mutating sensitif."""

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        *,
        aksi: str,
        id_staf: Optional[int] = None,
        tabel_target: Optional[str] = None,
        id_target: Optional[int] = None,
        data_lama: Optional[dict[str, Any]] = None,
        data_baru: Optional[dict[str, Any]] = None,
        keterangan: Optional[str] = None,
        status_aksi: StatusAksiAuditEnum = StatusAksiAuditEnum.SUCCESS,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """
        Catat 1 event audit.

        Tidak commit — caller yang manage transaction. Kalau gagal,
        log error tapi tidak raise (audit failure tidak boleh block business).
        """
        try:
            ip_address = None
            user_agent = None
            endpoint = None
            http_method = None
            if request is not None:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
                endpoint = str(request.url.path)
                http_method = request.method

            entry = AuditLog(
                id_staf=id_staf,
                aksi=aksi,
                tabel_target=tabel_target,
                id_target=id_target,
                data_lama=data_lama,
                data_baru=data_baru,
                ip_address=ip_address,
                user_agent=user_agent,
                endpoint=endpoint,
                http_method=http_method,
                keterangan=keterangan,
                status_aksi=status_aksi,
            )
            self.db.add(entry)
            self.db.flush()
            return entry
        except Exception as e:
            logger.error(f"Gagal tulis audit_log: {e}", exc_info=True)
            return None

    # ----- Shortcuts -----
    def log_login(
        self,
        id_staf: int,
        username: str,
        success: bool,
        request: Optional[Request] = None,
        keterangan: Optional[str] = None,
    ) -> Optional[AuditLog]:
        return self.log(
            aksi="LOGIN" if success else "LOGIN_FAILED",
            id_staf=id_staf if success else None,
            tabel_target="master_staf",
            id_target=id_staf,
            keterangan=keterangan or f"Login attempt by '{username}'",
            status_aksi=StatusAksiAuditEnum.SUCCESS if success else StatusAksiAuditEnum.FAILED,
            request=request,
        )

    def log_logout(
        self,
        id_staf: int,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        return self.log(
            aksi="LOGOUT",
            id_staf=id_staf,
            tabel_target="master_staf",
            id_target=id_staf,
            request=request,
        )

    def log_view(
        self,
        id_staf: int,
        id_pasien: int,
        keterangan: Optional[str] = None,
        request: Optional[Request] = None,
        commit: bool = True,
    ) -> Optional[AuditLog]:
        """Audit AKSES-BACA rekam medis (V7.2.1): catat siapa MEMBUKA data pasien mana.

        Dipanggil di endpoint GET (baca) → commit sendiri (tak ada transaksi bisnis lain).
        Kegagalan audit tidak boleh memblokir tampilan halaman.
        """
        entry = self.log(
            aksi="VIEW",
            id_staf=id_staf,
            tabel_target="pasien",
            id_target=id_pasien,
            keterangan=keterangan or "Buka rekam medis pasien",
            request=request,
        )
        if commit:
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
        return entry

    def log_create(
        self,
        id_staf: int,
        tabel: str,
        id_target: int,
        data_baru: dict[str, Any],
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        return self.log(
            aksi="CREATE",
            id_staf=id_staf,
            tabel_target=tabel,
            id_target=id_target,
            data_baru=data_baru,
            request=request,
        )

    def log_update(
        self,
        id_staf: int,
        tabel: str,
        id_target: int,
        data_lama: dict[str, Any],
        data_baru: dict[str, Any],
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        return self.log(
            aksi="UPDATE",
            id_staf=id_staf,
            tabel_target=tabel,
            id_target=id_target,
            data_lama=data_lama,
            data_baru=data_baru,
            request=request,
        )

    def log_delete(
        self,
        id_staf: int,
        tabel: str,
        id_target: int,
        data_lama: dict[str, Any],
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        return self.log(
            aksi="DELETE",
            id_staf=id_staf,
            tabel_target=tabel,
            id_target=id_target,
            data_lama=data_lama,
            request=request,
        )

    def log_void(
        self,
        id_staf: int,
        tabel: str,
        id_target: int,
        keterangan: str,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """Void item (resep, transaksi). Butuh keterangan alasan."""
        return self.log(
            aksi="VOID",
            id_staf=id_staf,
            tabel_target=tabel,
            id_target=id_target,
            keterangan=keterangan,
            request=request,
        )


__all__ = ["AuditService"]
