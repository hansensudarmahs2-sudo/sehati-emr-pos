"""
Sehati Clinic — Database Backup Script.

Backup MySQL database + folder uploads ke file ZIP terkompresi.
Auto-purge backup file lebih lama dari RETENTION_DAYS.

Usage:
    python scripts/backup.py              # Run backup (default)
    python scripts/backup.py --dry-run    # Simulasi tanpa write file
    python scripts/backup.py --list       # List existing backups
    python scripts/backup.py --no-purge   # Skip auto-purge
    python scripts/backup.py --help       # Bantuan

Lokasi backup: sehati_clinic/backups/backup_YYYYMMDD_HHMMSS.zip
Retention: 30 hari (auto-purge file yang lebih lama)
Isi ZIP:
    - sehati_db.sql        — mysqldump file
    - uploads/             — folder logo/file upload
    - BACKUP_INFO.txt      — metadata (timestamp, size, host, dbname)

Prasyarat:
    - mysqldump tersedia di PATH (Windows: C:\\xampp\\mysql\\bin\\mysqldump.exe)
    - Credentials DB di .env (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)

Author: Claude (Lead Programmer untuk dr. Hansen Sudarma)
Last update: 6 Juni 2026
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# Konstanta
RETENTION_DAYS = 30
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKUPS_DIR = PROJECT_DIR / "backups"
UPLOADS_DIR = PROJECT_DIR / "static" / "uploads"
LOG_FILE = BACKUPS_DIR / "backup_log.txt"


def _load_db_config() -> dict:
    """
    Load DB credentials dari .env. Kalau .env tidak ada, fallback ke
    environment variables. Tidak panggil app.config supaya script ini
    portable & tidak ter-import side effect dari app.
    """
    env_file = PROJECT_DIR / ".env"
    cfg = {
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_USER": "klinik_dev",
        "DB_PASSWORD": "",
        "DB_NAME": "db_sehati",
    }
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().upper()
            value = value.strip().strip('"').strip("'")
            if key in cfg:
                cfg[key] = value
    # Override dari env vars kalau ada
    for k in cfg:
        if k in os.environ:
            cfg[k] = os.environ[k]
    return cfg


def _find_mysqldump() -> str:
    """Cari executable mysqldump di PATH. Windows-friendly fallbacks."""
    candidates = [
        "mysqldump",
        r"C:\xampp\mysql\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
        r"C:\Program Files\MariaDB 10.6\bin\mysqldump.exe",
        "/usr/bin/mysqldump",
    ]
    for c in candidates:
        path = shutil.which(c) if not os.path.isabs(c) else (c if os.path.isfile(c) else None)
        if path:
            return path
    raise FileNotFoundError(
        "mysqldump tidak ditemukan. Pastikan MySQL/MariaDB ter-install dan "
        "mysqldump tersedia di PATH. Bila pakai XAMPP, tambahkan "
        "C:\\xampp\\mysql\\bin\\ ke PATH lalu coba lagi."
    )


def _log(message: str) -> None:
    """Tulis ke log file + print ke stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        pass  # logging optional


def _human_bytes(num: int) -> str:
    """Format byte → human readable."""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def _sha256_file(path: Path) -> str:
    """Hash SHA-256 file untuk integrity check."""
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _do_mysqldump(cfg: dict, output_sql: Path) -> None:
    """Run mysqldump → simpan ke output_sql."""
    mysqldump = _find_mysqldump()
    cmd = [
        mysqldump,
        f"-h{cfg['DB_HOST']}",
        f"-P{cfg['DB_PORT']}",
        f"-u{cfg['DB_USER']}",
        f"-p{cfg['DB_PASSWORD']}",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--default-character-set=utf8mb4",
        "--add-drop-table",
        cfg["DB_NAME"],
    ]
    _log(f"Running mysqldump untuk database '{cfg['DB_NAME']}'...")
    with output_sql.open("wb") as fp:
        result = subprocess.run(
            cmd, stdout=fp, stderr=subprocess.PIPE, check=False,
        )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"mysqldump exit code {result.returncode}.\nSTDERR:\n{stderr}"
        )
    sz = output_sql.stat().st_size
    _log(f"  ✓ SQL dump berhasil: {_human_bytes(sz)}")


def _build_zip(sql_path: Path, output_zip: Path) -> None:
    """ZIP: sehati_db.sql + uploads/ + BACKUP_INFO.txt."""
    _log(f"Membuat ZIP: {output_zip.name}")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. SQL dump
        zf.write(sql_path, arcname="sehati_db.sql")

        # 2. uploads/ folder
        uploads_count = 0
        if UPLOADS_DIR.exists():
            for fpath in UPLOADS_DIR.rglob("*"):
                if fpath.is_file():
                    rel = fpath.relative_to(UPLOADS_DIR.parent)
                    zf.write(fpath, arcname=str(rel).replace("\\", "/"))
                    uploads_count += 1
        _log(f"  ✓ Uploads: {uploads_count} file")

        # 3. Source code (DEC-061 — recovery dari B-013 cascade)
        source_count = 0
        project_root = sql_path.parent.parent  # = sehati_clinic/
        source_dirs = ["app", "migrations_sql", "seed_data", "scripts", "Project_Memory"]
        exclude_parts = {"__pycache__", ".pytest_cache", ".venv", "node_modules", ".mypy_cache"}
        exclude_suffix = {".pyc", ".pyo"}
        for src_dir in source_dirs:
            src_path = project_root / src_dir
            if not src_path.exists():
                # Project_Memory mungkin di parent (WebApp for eMR and POS/Project_Memory)
                src_path = project_root.parent / src_dir
                if not src_path.exists():
                    continue
            for fpath in src_path.rglob("*"):
                if not fpath.is_file():
                    continue
                if any(part in exclude_parts for part in fpath.parts):
                    continue
                if fpath.suffix in exclude_suffix:
                    continue
                rel = fpath.relative_to(src_path.parent)
                zf.write(fpath, arcname=f"source/{str(rel).replace(chr(92), '/')}")
                source_count += 1
        _log(f"  ✓ Source code: {source_count} file")

        # 4. Metadata
        sql_hash = _sha256_file(sql_path)
        cfg = _load_db_config()
        info = (
            f"Sehati Clinic — Backup Info\n"
            f"============================\n"
            f"Created     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Hostname    : {os.environ.get('COMPUTERNAME', 'unknown')}\n"
            f"DB host     : {cfg['DB_HOST']}:{cfg['DB_PORT']}\n"
            f"DB name     : {cfg['DB_NAME']}\n"
            f"DB user     : {cfg['DB_USER']}\n"
            f"SQL size    : {_human_bytes(sql_path.stat().st_size)}\n"
            f"SQL SHA-256 : {sql_hash}\n"
            f"Uploads     : {uploads_count} file\n"
            f"Source code : {source_count} file (DEC-061)\n"
            f"\n"
            f"CARA RESTORE:\n"
            f"  python scripts/restore.py {output_zip.name}\n"
            f"\n"
            f"Atau manual:\n"
            f"  1. Extract ZIP ke folder kosong\n"
            f"  2. mysql -u root -p db_sehati < sehati_db.sql\n"
            f"  3. Copy folder uploads/ ke sehati_clinic/static/\n"
        )
        zf.writestr("BACKUP_INFO.txt", info)


def _purge_old_backups(keep_days: int) -> int:
    """Hapus file backup_*.zip yang lebih lama dari keep_days. Return count."""
    if not BACKUPS_DIR.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    purged = 0
    for f in BACKUPS_DIR.glob("backup_*.zip"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                purged += 1
                _log(f"  ✗ Purged: {f.name} (umur {(datetime.now()-mtime).days} hari)")
        except Exception as exc:
            _log(f"  ! Gagal purge {f.name}: {exc}")
    return purged


def _list_backups() -> None:
    """List backup file di backups/ dengan size + tanggal."""
    if not BACKUPS_DIR.exists():
        print("Folder backups/ belum ada.")
        return
    files = sorted(BACKUPS_DIR.glob("backup_*.zip"), reverse=True)
    if not files:
        print("Belum ada backup file.")
        return
    print(f"{'File':<40s} {'Size':>10s}   {'Tanggal':>20s}")
    print("-" * 75)
    total_size = 0
    for f in files:
        size = f.stat().st_size
        total_size += size
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{f.name:<40s} {_human_bytes(size):>10s}   {mtime:>20s}")
    print("-" * 75)
    print(f"Total: {len(files)} file, {_human_bytes(total_size)}")


def run_backup(dry_run: bool = False, do_purge: bool = True) -> Path | None:
    """Main backup workflow. Return path ZIP yang dibuat, atau None kalau dry-run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"backup_{timestamp}.zip"
    zip_path = BACKUPS_DIR / zip_name

    if dry_run:
        _log("=== DRY RUN MODE — tidak akan tulis file ===")
        cfg = _load_db_config()
        try:
            mysqldump = _find_mysqldump()
            _log(f"  ✓ mysqldump found: {mysqldump}")
        except FileNotFoundError as e:
            _log(f"  ✗ {e}")
            return None
        _log(f"  ✓ DB config: {cfg['DB_USER']}@{cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}")
        _log(f"  ✓ Uploads dir: {UPLOADS_DIR} (exists: {UPLOADS_DIR.exists()})")
        _log(f"  ✓ Output: {zip_path}")
        _log(f"  ✓ Retention: {RETENTION_DAYS} hari")
        _log("=== DRY RUN OK — backup actual akan jalan tanpa flag --dry-run ===")
        return None

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"=== Backup mulai: {timestamp} ===")

    cfg = _load_db_config()
    temp_sql = BACKUPS_DIR / f"_temp_{timestamp}.sql"

    try:
        _do_mysqldump(cfg, temp_sql)
        _build_zip(temp_sql, zip_path)
        zip_size = zip_path.stat().st_size
        _log(f"  ✓ ZIP berhasil: {_human_bytes(zip_size)} → {zip_path}")
    except Exception as exc:
        _log(f"  ✗ Backup gagal: {exc}")
        # Cleanup temp file kalau ada
        if temp_sql.exists():
            try: temp_sql.unlink()
            except Exception: pass
        if zip_path.exists():
            try: zip_path.unlink()
            except Exception: pass
        raise
    finally:
        # Hapus temp SQL file
        if temp_sql.exists():
            try: temp_sql.unlink()
            except Exception: pass

    # Auto-purge
    if do_purge:
        _log(f"Auto-purge backup lebih lama dari {RETENTION_DAYS} hari...")
        n = _purge_old_backups(RETENTION_DAYS)
        if n:
            _log(f"  ✓ {n} file lama dihapus")
        else:
            _log(f"  ✓ Tidak ada file untuk di-purge")

    _log(f"=== Backup selesai: {zip_path.name} ===\n")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sehati Clinic — Backup Script (mysqldump + uploads)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python scripts/backup.py              # Run backup\n"
            "  python scripts/backup.py --dry-run    # Cek config tanpa write\n"
            "  python scripts/backup.py --list       # List backup existing\n"
            "  python scripts/backup.py --no-purge   # Skip auto-purge\n"
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Cek setup tanpa write file backup")
    parser.add_argument("--list", action="store_true",
                        help="List backup file existing")
    parser.add_argument("--no-purge", action="store_true",
                        help="Skip auto-purge backup lama")
    args = parser.parse_args()

    if args.list:
        _list_backups()
        return 0

    try:
        run_backup(dry_run=args.dry_run, do_purge=not args.no_purge)
        return 0
    except FileNotFoundError as e:
        print(f"\n❌ ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\n❌ Backup gagal: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
