#!/usr/bin/env python3
"""
DB Integrity Health Check — Sehati Clinic

Jalankan dari root project sehati_clinic:
    cd /path/to/sehati_clinic
    python ../Project_Memory/HealthCheck/scripts/db_integrity.py

Output: markdown ke stdout. Master runner akan capture dan gabung ke log harian.
"""

import sys
from pathlib import Path

# Cari root project sehati_clinic — script ini biasanya di Project_Memory/HealthCheck/scripts/
HERE = Path(__file__).resolve().parent
PROJECT_ROOT_CANDIDATES = [
    HERE.parents[2] / "sehati_clinic",  # ../../sehati_clinic
    HERE.parents[1] / "sehati_clinic",
    Path.cwd() / "sehati_clinic",
    Path.cwd(),
]
SEHATI_ROOT = next((p for p in PROJECT_ROOT_CANDIDATES if (p / "app" / "config.py").exists()), None)
if SEHATI_ROOT is None:
    print("ERROR: Cannot find sehati_clinic project root.")
    sys.exit(1)

sys.path.insert(0, str(SEHATI_ROOT))

from sqlalchemy import text  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


# =============================================================================
# Check definitions
# =============================================================================

CHECKS = [
    # (code, severity, label, sql, expected_zero)
    ("DB-01", "CRITICAL", "Stok produk negatif",
     "SELECT COUNT(*) FROM master_produk WHERE stok_terkini < 0", True),
    ("DB-02", "CRITICAL", "Stok bahan negatif",
     "SELECT COUNT(*) FROM inventory_stok WHERE stok_terkini < 0", True),
    ("DB-03", "HIGH", "Inventory_history XOR violation (id_produk dan id_bahan dua-duanya NULL atau dua-duanya terisi)",
     """SELECT COUNT(*) FROM inventory_history
        WHERE (id_produk IS NULL AND id_bahan IS NULL)
           OR (id_produk IS NOT NULL AND id_bahan IS NOT NULL)""", True),
    ("DB-04", "CRITICAL", "Master_staf tanpa password_hash",
     "SELECT COUNT(*) FROM master_staf WHERE password_hash IS NULL OR password_hash = ''", True),
    ("DB-05", "HIGH", "Master_staf dengan role tidak dikenali",
     """SELECT COUNT(*) FROM master_staf
        WHERE role NOT IN ('OWNER','SUPERADMIN','ADMIN','DOKTER','PERAWAT','FO','KASIR','APOTEKER','PURCHASING')""", True),
    ("DB-06", "HIGH", "Kunjungan tanpa pasien (FK orphan)",
     """SELECT COUNT(*) FROM kunjungan k
        LEFT JOIN pasien p ON p.id_pasien = k.id_pasien
        WHERE p.id_pasien IS NULL""", True),
    ("DB-07", "MEDIUM", "Audit log tanpa id_staf untuk aksi mutating",
     """SELECT COUNT(*) FROM audit_log
        WHERE id_staf IS NULL
          AND aksi NOT IN ('LOGIN_FAIL','LOGIN_SUCCESS','LOGOUT')""", True),
    ("DB-08", "HIGH", "Pemesanan_item tanpa parent pemesanan",
     """SELECT COUNT(*) FROM pemesanan_item pi
        LEFT JOIN pemesanan p ON p.id_pemesanan = pi.id_pemesanan
        WHERE p.id_pemesanan IS NULL""", True),
    ("DB-09", "HIGH", "Pemesanan_receive dengan qty_diterima > qty_dipesan (item)",
     """SELECT COUNT(*) FROM pemesanan_item pi
        WHERE pi.qty_diterima > pi.qty_dipesan""", True),
    ("DB-10", "HIGH", "Stock_opname_item tanpa parent opname",
     """SELECT COUNT(*) FROM stock_opname_item soi
        LEFT JOIN stock_opname so ON so.id_opname = soi.id_opname
        WHERE so.id_opname IS NULL""", True),
    ("DB-11", "MEDIUM", "Transaksi_kasir tanpa kunjungan (FK orphan)",
     """SELECT COUNT(*) FROM transaksi_kasir tk
        LEFT JOIN kunjungan k ON k.id_kunjungan = tk.id_kunjungan
        WHERE k.id_kunjungan IS NULL""", True),
    ("DB-12", "MEDIUM", "Master_produk dengan stok_minimal negatif",
     "SELECT COUNT(*) FROM master_produk WHERE stok_minimal < 0", True),
    ("DB-13", "MEDIUM", "Pasien duplikat nomor_ktp",
     """SELECT COUNT(*) FROM (
            SELECT nomor_ktp FROM pasien
            WHERE nomor_ktp IS NOT NULL AND nomor_ktp != ''
            GROUP BY nomor_ktp HAVING COUNT(*) > 1
        ) AS dup""", True),
    ("DB-14", "MEDIUM", "Audit log entri terakhir > 7 hari (sistem mungkin tidak aktif)",
     """SELECT CASE WHEN MAX(waktu) IS NULL THEN 1
                    WHEN MAX(waktu) < NOW() - INTERVAL 7 DAY THEN 1
                    ELSE 0 END
        FROM audit_log""", True),
]


def main():
    db = SessionLocal()
    findings = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "PASS": []}
    errors = []

    for code, severity, label, sql, expected_zero in CHECKS:
        try:
            result = db.execute(text(sql)).scalar() or 0
            count = int(result)
            if expected_zero and count > 0:
                findings[severity].append({
                    "code": code, "label": label, "count": count,
                    "severity": severity, "sql": sql.strip(),
                })
            else:
                findings["PASS"].append({"code": code, "label": label})
        except Exception as e:
            errors.append({"code": code, "label": label, "error": str(e)})

    db.close()

    # ----- Output markdown -----
    total = len(CHECKS)
    fail_count = sum(len(findings[s]) for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    pass_count = len(findings["PASS"])
    err_count = len(errors)

    print(f"## 🗄  DB Integrity Check\n")
    print(f"- Total: **{total}**")
    print(f"- ✓ Pass: **{pass_count}**")
    print(f"- ✗ Fail: **{fail_count}**")
    if err_count:
        print(f"- ⚠ Errors (gagal dieksekusi): **{err_count}**")
    print()

    if findings["CRITICAL"]:
        print("### 🔴 CRITICAL\n")
        for f in findings["CRITICAL"]:
            print(f"- **[{f['code']}]** {f['label']} → **{f['count']}** record")
        print()

    if findings["HIGH"]:
        print("### 🟠 HIGH\n")
        for f in findings["HIGH"]:
            print(f"- **[{f['code']}]** {f['label']} → **{f['count']}** record")
        print()

    if findings["MEDIUM"]:
        print("### 🟡 MEDIUM\n")
        for f in findings["MEDIUM"]:
            print(f"- **[{f['code']}]** {f['label']} → **{f['count']}** record")
        print()

    if errors:
        print("### ⚠ Errors (check gagal dieksekusi, mungkin tabel belum dibuat)\n")
        for e in errors:
            print(f"- **[{e['code']}]** {e['label']}")
            print(f"  - Error: `{e['error'][:200]}`")
        print()

    if fail_count == 0 and err_count == 0:
        print("✅ Semua DB integrity check lulus.\n")

    # Exit code: 1 kalau ada CRITICAL atau HIGH
    if findings["CRITICAL"] or findings["HIGH"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
