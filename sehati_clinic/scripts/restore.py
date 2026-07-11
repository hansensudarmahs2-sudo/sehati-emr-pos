"""
Sehati Clinic — Database Restore Script.

Restore database + uploads dari file ZIP backup yang dihasilkan backup.py.

SAFETY FIRST:
1. Script ini SELALU buat backup state sekarang dulu sebelum restore.
2. Wajib confirm sebelum eksekusi (kecuali pakai flag --yes).
3. Show preview isi ZIP + metadata dulu.

Usage:
    python scripts/restore.py backups/backup_20260605_223030.zip
    python scripts/restore.py backup_20260605_223030.zip      # auto-resolve di backups/
    python scripts/restore.py --info backup.zip               # cek isi tanpa restore
    python scripts/restore.py backup.zip --yes                # skip confirm prompt
    python scripts/restore.py --help                          # bantuan

Tahapan restore:
    1. Validate ZIP file ada + bisa dibuka
    2. Show metadata + isi ZIP
    3. Confirm (atau --yes)
    4. Auto-backup state sekarang dulu → backups/pre_restore_*.zip
    5. Extract SQL dump + uploads ke folder temp
    6. Drop + recreate database via mysql command
    7. Restore uploads/ ke static/uploads/

Author: Claude (Lead Programmer untuk dr. Hansen Sudarma)
Last update: 6 Juni 2026
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# Import shared helpers dari backup.py
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKUPS_DIR = PROJECT_DIR / "backups"
UPLOADS_DIR = PROJECT_DIR / "static" / "uploads"

sys.path.insert(0, str(SCRIPT_DIR))
from backup import _load_db_config, _human_bytes, run_backup  # noqa: E402


def _find_mysql_client() -> str:
    """Cari executable mysql client di PATH."""
    candidates = [
        "mysql",
        r"C:\xampp\mysql\bin\mysql.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        r"C:\Program Files\MariaDB 10.6\bin\mysql.exe",
        "/usr/bin/mysql",
    ]
    for c in candidates:
        path = shutil.which(c) if not os.path.isabs(c) else (c if os.path.isfile(c) else None)
        if path:
            return path
    raise FileNotFoundError(
        "mysql client tidak ditemukan. Install MySQL client atau tambah path-nya ke PATH."
    )


def _resolve_zip_path(arg: str) -> Path:
    """
    Resolve path ZIP:
    - Kalau absolute path / relatif yang exists → pakai langsung
    - Kalau hanya filename → cari di backups/ dir
    """
    p = Path(arg)
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p.resolve()
    # Coba di backups/
    candidate = BACKUPS_DIR / arg
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Backup file tidak ditemukan: {arg}")


def _read_zip_info(zip_path: Path) -> dict:
    """Baca BACKUP_INFO.txt + list isi ZIP."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"{zip_path.name} bukan file ZIP yang valid.")

    info = {"path": zip_path, "size": zip_path.stat().st_size, "files": [], "metadata": ""}
    with zipfile.ZipFile(zip_path, "r") as zf:
        info["files"] = zf.namelist()
        if "BACKUP_INFO.txt" in info["files"]:
            info["metadata"] = zf.read("BACKUP_INFO.txt").decode("utf-8", errors="replace")
    return info


def _show_zip_preview(info: dict) -> None:
    """Tampilkan isi ZIP + metadata."""
    print(f"\n📦 Backup file: {info['path'].name}")
    print(f"   Size: {_human_bytes(info['size'])}")
    print(f"   Files in ZIP: {len(info['files'])}")
    print()
    has_sql = "sehati_db.sql" in info["files"]
    n_uploads = sum(1 for f in info["files"] if f.startswith("uploads/"))
    print(f"   ✓ sehati_db.sql: {'YES' if has_sql else 'MISSING ⚠'}")
    print(f"   ✓ uploads/: {n_uploads} file")
    print()
    if info["metadata"]:
        print("--- BACKUP_INFO.txt ---")
        print(info["metadata"])
        print("--- end metadata ---\n")


def _confirm(prompt: str) -> bool:
    """Y/n prompt, default n."""
    try:
        response = input(f"{prompt} (ketik 'RESTORE' untuk confirm): ").strip()
    except (KeyboardInterrupt, EOFError):
        return False
    return response == "RESTORE"


def _do_pre_restore_backup() -> Path | None:
    """Auto-backup state sekarang sebelum restore. Return path hasil."""
    print("\n🔒 Auto-backup state sekarang dulu (safety net)...")
    try:
        # Override default zip naming via timestamp prefix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Just call run_backup; the file will be backup_{timestamp}.zip
        result = run_backup(dry_run=False, do_purge=False)
        if result:
            # Rename to pre_restore_*
            new_name = result.parent / f"pre_restore_{timestamp}.zip"
            result.rename(new_name)
            print(f"   ✓ Pre-restore backup: {new_name.name}")
            return new_name
    except Exception as e:
        print(f"   ⚠ Pre-restore backup gagal: {e}")
        print("   Lanjut restore? Tanpa safety net, kalau gagal data hilang!")
        if not _confirm("Lanjut tanpa pre-restore backup?"):
            return None
    return None


def _restore_database(sql_path: Path, cfg: dict) -> None:
    """Run mysql client → import SQL dump ke database."""
    mysql = _find_mysql_client()
    cmd = [
        mysql,
        f"-h{cfg['DB_HOST']}",
        f"-P{cfg['DB_PORT']}",
        f"-u{cfg['DB_USER']}",
        f"-p{cfg['DB_PASSWORD']}",
        cfg["DB_NAME"],
    ]
    print(f"\n🗃 Restoring database '{cfg['DB_NAME']}'...")
    with sql_path.open("rb") as fp:
        result = subprocess.run(cmd, stdin=fp, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"mysql restore exit code {result.returncode}.\nSTDERR:\n{stderr}"
        )
    print(f"   ✓ Database '{cfg['DB_NAME']}' berhasil di-restore")


def _restore_uploads(extract_dir: Path) -> int:
    """Copy uploads dari extract dir ke static/uploads/."""
    src = extract_dir / "uploads"
    if not src.exists():
        print("   ⓘ Tidak ada folder uploads/ di backup")
        return 0
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            dst = UPLOADS_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            count += 1
    print(f"   ✓ Uploads: {count} file di-restore ke {UPLOADS_DIR}")
    return count


def run_restore(zip_path: Path, skip_confirm: bool = False, skip_pre_backup: bool = False) -> None:
    """Main restore workflow."""
    info = _read_zip_info(zip_path)
    _show_zip_preview(info)

    if not skip_confirm:
        print("⚠ PERHATIAN: Restore akan REPLACE database saat ini.")
        print("⚠ Data sekarang akan di-overwrite. Pre-restore backup otomatis dibuat sebagai safety.")
        if not _confirm("\nLanjut restore?"):
            print("\nRestore dibatalkan.")
            return

    pre_backup_path = None
    if not skip_pre_backup:
        pre_backup_path = _do_pre_restore_backup()

    cfg = _load_db_config()

    # Extract ke temp dir
    with tempfile.TemporaryDirectory(prefix="sehati_restore_") as tmp:
        tmp_path = Path(tmp)
        print(f"\n📂 Extracting ZIP ke temp dir...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)
        sql_file = tmp_path / "sehati_db.sql"
        if not sql_file.exists():
            raise FileNotFoundError("sehati_db.sql tidak ditemukan dalam ZIP")
        print(f"   ✓ Extracted ke {tmp_path}")

        # Restore DB
        _restore_database(sql_file, cfg)

        # Restore uploads
        _restore_uploads(tmp_path)

    print("\n✅ Restore selesai!")
    print(f"   Database: {cfg['DB_NAME']}")
    if pre_backup_path:
        print(f"   Pre-restore backup tersimpan: {pre_backup_path.name}")
    print("\n   Silakan restart aplikasi (uvicorn) untuk pakai data baru.\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sehati Clinic — Restore Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python scripts/restore.py backup_20260605_223030.zip\n"
            "  python scripts/restore.py --info backup_20260605_223030.zip\n"
            "  python scripts/restore.py backup.zip --yes --skip-pre-backup\n"
        ),
    )
    parser.add_argument("zipfile", nargs="?", help="Path/nama file backup ZIP")
    parser.add_argument("--info", action="store_true",
                        help="Show isi ZIP saja, tidak restore")
    parser.add_argument("--yes", action="store_true",
                        help="Skip confirm prompt (DANGEROUS — pastikan zipnya benar)")
    parser.add_argument("--skip-pre-backup", action="store_true",
                        help="Skip auto-backup state sebelum restore (NOT RECOMMENDED)")
    args = parser.parse_args()

    if not args.zipfile:
        parser.print_help()
        return 1

    try:
        zip_path = _resolve_zip_path(args.zipfile)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    if args.info:
        try:
            info = _read_zip_info(zip_path)
            _show_zip_preview(info)
            return 0
        except Exception as e:
            print(f"❌ Gagal baca ZIP: {e}", file=sys.stderr)
            return 1

    try:
        run_restore(
            zip_path,
            skip_confirm=args.yes,
            skip_pre_backup=args.skip_pre_backup,
        )
        return 0
    except FileNotFoundError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\n❌ Restore gagal: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
