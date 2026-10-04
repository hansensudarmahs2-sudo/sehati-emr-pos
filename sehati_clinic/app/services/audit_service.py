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


def _potong(kolom: str, nilai: Optional[str]) -> Optional[str]:
    """Potong nilai ke lebar kolom `audit_log.<kolom>` (T24, audit alur uang 2026-10-04).

    MySQL produksi berjalan STRICT_TRANS_TABLES: nilai kepanjangan DITOLAK, bukan
    dipotong diam-diam. Dulu satu User-Agent 314 karakter (perangkat lunak keamanan,
    browser bawaan Android) membuat SETIAP aksi ber-audit pengguna itu gagal.
    Lebar dibaca dari model supaya tidak ada angka 255/50 kedua yang bisa basi.
    """
    if nilai is None:
        return None
    lebar = getattr(AuditLog.__table__.c[kolom].type, "length", None)
    return nilai[:lebar] if lebar else nilai


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

        ⚠ Ditulis di dalam SAVEPOINT (T23, keputusan dr. Hansen 2026-10-05:
        "aksi tetap jalan, kegagalan audit juga tercatat"). Dulu flush() langsung di
        sesi bisnis; kalau gagal, exception ditelan TAPI sesinya sudah ditandai
        perlu-rollback, sehingga commit() milik caller gagal dengan
        PendingRollbackError — kebalikan dari niat docstring ini, dan pesan errornya
        tidak menyebut audit sama sekali. Savepoint membatasi kegagalan ke baris
        audit itu saja. Jangan kembalikan ke flush() biasa.
        """
        ip_address = None
        user_agent = None
        endpoint = None
        http_method = None
        try:
            if request is not None:
                ip_address = _potong("ip_address", request.client.host if request.client else None)
                user_agent = _potong("user_agent", request.headers.get("user-agent"))
                endpoint = _potong("endpoint", str(request.url.path))
                http_method = _potong("http_method", request.method)

            entry = AuditLog(
                id_staf=id_staf,
                aksi=_potong("aksi", aksi),
                tabel_target=_potong("tabel_target", tabel_target),
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
            with self.db.begin_nested():
                self.db.add(entry)
            return entry
        except Exception as e:
            logger.error(f"Gagal tulis audit_log: {e}", exc_info=True)
            self._catat_kegagalan(
                aksi=aksi, id_staf=id_staf, tabel_target=tabel_target,
                id_target=id_target, galat=e, ip_address=ip_address,
                endpoint=endpoint, http_method=http_method,
            )
            return None

    def _catat_kegagalan(
        self,
        *,
        aksi: str,
        id_staf: Optional[int],
        tabel_target: Optional[str],
        id_target: Optional[int],
        galat: Exception,
        ip_address: Optional[str],
        endpoint: Optional[str],
        http_method: Optional[str],
    ) -> None:
        """Tulis baris pengganti `AUDIT_GAGAL` supaya kegagalannya terlihat di jejak audit.

        Sengaja minimal: tanpa data_lama/data_baru/user_agent (yang mungkin justru
        penyebab gagalnya). Kalau baris ini pun gagal, yang tersisa hanya log aplikasi
        di atas — tidak ada percobaan ketiga.
        Ikut transaksi bisnis: kalau aksinya di-rollback, catatan gagalnya ikut hilang,
        dan itu benar — aksinya memang tidak pernah terjadi.
        """
        try:
            with self.db.begin_nested():
                self.db.add(AuditLog(
                    id_staf=id_staf,
                    aksi="AUDIT_GAGAL",
                    tabel_target=_potong("tabel_target", tabel_target),
                    id_target=id_target,
                    ip_address=ip_address,
                    endpoint=endpoint,
                    http_method=http_method,
                    keterangan=f"Audit '{aksi}' gagal ditulis: {type(galat).__name__}: {str(galat)[:500]}",
                    status_aksi=StatusAksiAuditEnum.FAILED,
                ))
        except Exception:
            logger.error("Baris AUDIT_GAGAL pun gagal ditulis", exc_info=True)

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
