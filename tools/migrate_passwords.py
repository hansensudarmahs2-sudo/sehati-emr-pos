"""
migrate_passwords.py — One-shot script untuk hash password & PIN di db_sehati.

USAGE:
    python tools/migrate_passwords.py

PREREQUISITES:
    - Database backup sudah dibuat (lihat migrations/sql/README.md)
    - Migrasi 001-004 sudah dijalankan
    - Library terinstall:
        pip install pymysql bcrypt python-dotenv

WHAT IT DOES:
    1. Connect ke db_sehati (config dari .env)
    2. Untuk setiap row di master_staf:
       - Cek apakah password_hash sudah seperti bcrypt (mulai $2b$/$2a$/$2y$)
       - Kalau plaintext, hash dengan bcrypt → update kolom
       - Sama untuk PIN
    3. Print summary

NOTES:
    - Bcrypt punya limit 72 byte. Kalau password > 72 byte, otomatis di-truncate.
      Pas login nanti, app juga harus truncate input ke 72 byte sebelum verify.
    - Idempotent: aman dijalankan berkali-kali (skip row yang sudah di-hash).
    - Pakai transaction (rollback kalau error di tengah).
"""

import os
import sys

try:
    import pymysql
    import bcrypt
    from dotenv import load_dotenv
except ImportError as e:
    print(f"❌ Library belum terinstall: {e}")
    print("   Run: pip install pymysql bcrypt python-dotenv")
    sys.exit(1)


# ----- Config -----
load_dotenv()  # baca .env kalau ada

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "klinik_dev")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Klinik123!")  # default sesuai kode lama dokter
DB_NAME = os.getenv("DB_NAME", "db_sehati")

BCRYPT_MAX_BYTES = 72  # bcrypt hard limit


def is_already_bcrypt(value: str) -> bool:
    """Bcrypt hashes start with $2a$, $2b$, or $2y$."""
    if not value:
        return False
    return value.startswith(("$2a$", "$2b$", "$2y$"))


def hash_value(plaintext: str) -> tuple[str, bool]:
    """
    Hash plaintext dengan bcrypt. Return (hash, was_truncated).
    Kalau plaintext > 72 byte, truncate dulu (bcrypt limit).
    """
    if plaintext is None:
        plaintext = ""
    pw_bytes = plaintext.encode("utf-8")
    was_truncated = len(pw_bytes) > BCRYPT_MAX_BYTES
    if was_truncated:
        pw_bytes = pw_bytes[:BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8"), was_truncated


def main():
    print("=" * 70)
    print("MIGRATE PASSWORDS & PIN — db_sehati.master_staf")
    print("=" * 70)

    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    except Exception as e:
        print(f"❌ Gagal connect ke DB: {e}")
        sys.exit(1)

    print(f"✅ Connected ke {DB_HOST}:{DB_PORT}/{DB_NAME}")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id_staf, username, password_hash, pin FROM master_staf"
            )
            rows = cursor.fetchall()
            print(f"📋 Ditemukan {len(rows)} row di master_staf.")
            print()

            stats = {
                "password_hashed": 0,
                "password_skipped": 0,
                "password_truncated": 0,
                "pin_hashed": 0,
                "pin_skipped": 0,
                "pin_null": 0,
                "pin_truncated": 0,
            }

            for row in rows:
                id_staf = row["id_staf"]
                username = row["username"] or ""
                pw_now = row["password_hash"]
                pin_now = row["pin"]

                updates = {}

                # --- Password ---
                if is_already_bcrypt(pw_now):
                    print(f"  [{id_staf}] {username:20} password: SKIP (sudah bcrypt)")
                    stats["password_skipped"] += 1
                else:
                    pw_hashed, was_truncated = hash_value(pw_now or "")
                    updates["password_hash"] = pw_hashed
                    preview = (pw_now or "")[:3]
                    trunc_note = " [TRUNCATED ke 72 byte]" if was_truncated else ""
                    print(f"  [{id_staf}] {username:20} password: HASH "
                          f"(plaintext '{preview}***' → bcrypt){trunc_note}")
                    stats["password_hashed"] += 1
                    if was_truncated:
                        stats["password_truncated"] += 1

                # --- PIN ---
                if pin_now is None or pin_now == "":
                    print(f"  [{id_staf}] {username:20} pin     : NULL (skip)")
                    stats["pin_null"] += 1
                elif is_already_bcrypt(pin_now):
                    print(f"  [{id_staf}] {username:20} pin     : SKIP (sudah bcrypt)")
                    stats["pin_skipped"] += 1
                else:
                    pin_hashed, was_truncated = hash_value(pin_now)
                    updates["pin"] = pin_hashed
                    trunc_note = " [TRUNCATED ke 72 byte]" if was_truncated else ""
                    print(f"  [{id_staf}] {username:20} pin     : HASH{trunc_note}")
                    stats["pin_hashed"] += 1
                    if was_truncated:
                        stats["pin_truncated"] += 1

                if updates:
                    set_clause = ", ".join(f"{k} = %s" for k in updates)
                    values = list(updates.values()) + [id_staf]
                    cursor.execute(
                        f"UPDATE master_staf SET {set_clause} WHERE id_staf = %s",
                        values,
                    )

            conn.commit()
            print()
            print("=" * 70)
            print("✅ COMMIT BERHASIL")
            print(f"   Password di-hash    : {stats['password_hashed']}"
                  f" (truncated: {stats['password_truncated']})")
            print(f"   Password skipped    : {stats['password_skipped']}")
            print(f"   PIN di-hash         : {stats['pin_hashed']}"
                  f" (truncated: {stats['pin_truncated']})")
            print(f"   PIN skipped         : {stats['pin_skipped']}")
            print(f"   PIN null            : {stats['pin_null']}")
            print("=" * 70)

            if stats["password_truncated"] > 0 or stats["pin_truncated"] > 0:
                print()
                print("⚠️  CATATAN TRUNCATION:")
                print("   Beberapa password/PIN dipotong ke 72 byte saat hashing.")
                print("   Saat login, app juga akan truncate input ke 72 byte sebelum")
                print("   verify — jadi password lama tetap bisa dipakai (tapi hanya")
                print("   72 byte pertama yang efektif).")
                print()

            if stats["password_hashed"] > 0 or stats["pin_hashed"] > 0:
                print("ℹ️  Password lama (plaintext) tetap bisa dipakai untuk login.")
                print("   Sistem akan bandingkan plaintext input dengan hash di DB.")
                print()

    except Exception as e:
        conn.rollback()
        print(f"❌ ERROR — rollback dipanggil: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
