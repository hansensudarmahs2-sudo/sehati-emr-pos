"""Pemeriksa Temuan 30 — obat berstatus DISERAHKAN yang lotnya TIDAK PERNAH keluar.

HANYA MEMBACA. Tidak menulis apa pun.

Kenapa ini perlu ada
--------------------
`serahkan_obat` tidak pernah diblokir oleh stok kurang — stok minus memang sengaja
diizinkan supaya operasional klinik tidak berhenti (`apotek_repo.py:193`). Kalau
stoknya kurang, FEFO hanya mengambil sebisanya dan selisihnya muncul sebagai
peringatan di pesan SATU transaksi penyerahan. Peringatan itu hilang begitu apoteker
menutup halaman, padahal akibatnya menetap: barisnya tercatat `DISERAHKAN` sementara
tidak ada barang yang keluar dari lot.

Itu berbahaya karena `DISERAHKAN` dibaca sebagai bukti "stok sudah dipotong" oleh
jalur void. Pemeriksa ini mengubah kejadian sekali-lewat itu menjadi keadaan yang
bisa dicari kapan saja, dari data yang sudah ada — tanpa kolom baru, tanpa migrasi.

Yang dilaporkan
---------------
  1. Baris resep DISERAHKAN yang qty-nya LEBIH BESAR dari jejak lot yang tercatat.
  2. Racikan DISERAHKAN yang punya bahan inventori tapi tidak punya jejak lot sama sekali.
  3. Dipisahkan dengan sengaja — yang TIDAK DAPAT DINILAI, supaya pemeriksa ini tidak
     berteriak serigala:
       • jejak gaya LAMA (`id_resep` NULL, sebelum task #54 2026-09-22) — per produk,
         bukan per baris, jadi tidak bisa dicocokkan per resep;
       • produk yang TIDAK PERNAH punya baris `stok_lot` — stoknya dikelola cache saja,
         jadi tidak adanya jejak memang wajar.

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_serah_tanpa_lot
Di laptop:  docker compose ... exec sehati-app python -m scripts.cek_serah_tanpa_lot
"""
from sqlalchemy import text

from app.db.session import SessionLocal

# Jejak per-baris (`id_resep` terisi) baru ada sejak task #54. Baris sebelum itu
# memakai jejak per-produk, dan mencocokkannya per resep akan selalu "kurang".
TASK_54_MULAI = "2026-09-22"


SQL_RESEP = text("""
SELECT r.id_resep, r.id_kunjungan, r.qty, r.waktu_serah,
       p.kode_produk, p.nama_produk,
       COALESCE(j.qty_jejak, 0)            AS qty_jejak,
       COALESCE(lama.n, 0)                 AS n_jejak_gaya_lama,
       COALESCE(ada_lot.n, 0)              AS n_lot_produk
  FROM kunjungan_resep r
  JOIN master_produk p ON p.id_produk = r.id_produk
  LEFT JOIN (SELECT id_resep, SUM(qty) AS qty_jejak
               FROM kunjungan_lot_terpakai WHERE id_resep IS NOT NULL
              GROUP BY id_resep) j ON j.id_resep = r.id_resep
  LEFT JOIN (SELECT id_kunjungan, id_produk, COUNT(*) AS n
               FROM kunjungan_lot_terpakai
              WHERE id_resep IS NULL AND id_kunjungan_racikan IS NULL
              GROUP BY id_kunjungan, id_produk) lama
         ON lama.id_kunjungan = r.id_kunjungan AND lama.id_produk = r.id_produk
  LEFT JOIN (SELECT id_produk, COUNT(*) AS n FROM stok_lot
              WHERE tipe_item = 'PRODUK' GROUP BY id_produk) ada_lot
         ON ada_lot.id_produk = r.id_produk
 WHERE r.status_item = 'DISERAHKAN'
 ORDER BY r.waktu_serah DESC, r.id_resep DESC
""")

SQL_RACIKAN = text("""
SELECT h.id_kunjungan_racikan, h.id_kunjungan, h.nama_snapshot, h.waktu_serah,
       COALESCE(b.n_bahan_inventori, 0) AS n_bahan_inventori,
       COALESCE(j.n_jejak, 0)           AS n_jejak
  FROM kunjungan_racikan h
  LEFT JOIN (SELECT id_kunjungan_racikan, COUNT(*) AS n_bahan_inventori
               FROM kunjungan_racikan_bahan
              WHERE id_produk IS NOT NULL AND dipakai > 0
              GROUP BY id_kunjungan_racikan) b
         ON b.id_kunjungan_racikan = h.id_kunjungan_racikan
  LEFT JOIN (SELECT id_kunjungan_racikan, COUNT(*) AS n_jejak
               FROM kunjungan_lot_terpakai WHERE id_kunjungan_racikan IS NOT NULL
              GROUP BY id_kunjungan_racikan) j
         ON j.id_kunjungan_racikan = h.id_kunjungan_racikan
 WHERE h.status_item = 'DISERAHKAN'
 ORDER BY h.waktu_serah DESC, h.id_kunjungan_racikan DESC
""")


def main() -> None:
    db = SessionLocal()
    try:
        temuan, tak_dinilai = [], []

        for r in db.execute(SQL_RESEP).mappings():
            selisih = float(r["qty"] or 0) - float(r["qty_jejak"] or 0)
            if selisih <= 1e-6:
                continue
            # Dua alasan sah untuk tidak punya jejak — bukan temuan.
            if r["n_jejak_gaya_lama"]:
                tak_dinilai.append(
                    f"resep #{r['id_resep']} ({r['nama_produk']}) — jejak gaya LAMA "
                    f"per produk, sebelum task #54"
                )
                continue
            if not r["n_lot_produk"]:
                tak_dinilai.append(
                    f"resep #{r['id_resep']} ({r['nama_produk']}) — produk ini TIDAK "
                    f"PERNAH punya lot; stoknya dikelola cache saja"
                )
                continue
            temuan.append({
                "apa": f"resep #{r['id_resep']}",
                "kunjungan": r["id_kunjungan"],
                "produk": f"{r['kode_produk']} {r['nama_produk']}",
                "qty": float(r["qty"] or 0),
                "jejak": float(r["qty_jejak"] or 0),
                "tanpa_jejak": selisih,
                "waktu": r["waktu_serah"],
            })

        for h in db.execute(SQL_RACIKAN).mappings():
            if not h["n_bahan_inventori"] or h["n_jejak"]:
                continue
            temuan.append({
                "apa": f"racikan #{h['id_kunjungan_racikan']}",
                "kunjungan": h["id_kunjungan"],
                "produk": f"⚗️ {h['nama_snapshot']}",
                "qty": float(h["n_bahan_inventori"]),
                "jejak": 0.0,
                "tanpa_jejak": float(h["n_bahan_inventori"]),
                "waktu": h["waktu_serah"],
            })

        print("PEMERIKSA: obat DISERAHKAN yang lotnya tidak pernah keluar "
              "(Temuan 30)\n")

        if temuan:
            print(f"  ✗ {len(temuan)} baris DISERAHKAN tanpa jejak lot yang cukup:\n")
            for t in temuan:
                print(f"      {t['apa']}  kunjungan #{t['kunjungan']}  {t['produk']}")
                print(f"        qty tercatat diserahkan : {t['qty']:g}")
                print(f"        qty yang benar-benar keluar dari lot : {t['jejak']:g}")
                print(f"        TANPA jejak lot : {t['tanpa_jejak']:g}"
                      f"   (waktu serah: {t['waktu']})")
            print("\n      Artinya: barisnya tercatat sudah diserahkan, tapi barangnya")
            print("      tidak pernah keluar dari lot mana pun. Nilai yang perlu")
            print("      diputuskan dr. Hansen: apakah pasiennya memang menerima obat")
            print("      (berarti lot/opname-nya yang salah) atau tidak menerima")
            print("      (berarti ada kewajiban yang belum dipenuhi).")
        else:
            print("  ✓ nihil — setiap baris DISERAHKAN punya jejak lot yang cukup")

        if tak_dinilai:
            print(f"\n  … {len(tak_dinilai)} baris TIDAK DAPAT DINILAI (bukan temuan):")
            for s in tak_dinilai[:20]:
                print(f"      • {s}")
            if len(tak_dinilai) > 20:
                print(f"      • … dan {len(tak_dinilai) - 20} lainnya")

        print(f"\nHASIL: {len(temuan)} temuan, {len(tak_dinilai)} tidak dapat dinilai")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
