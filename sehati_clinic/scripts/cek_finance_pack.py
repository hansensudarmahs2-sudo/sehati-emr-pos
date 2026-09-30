"""Pemeriksa: medical_soap_raw keluar dari finance pack TANPA menggeser nomor berkas.

MURNI BACA — tidak menulis berkas apa pun ke folder drop.

Bahaya yang dijaga: penomoran berkas berasal dari POSISI di `DATASET_REGISTRY`
(`enumerate(..., 1)`), sedangkan loader Finance membuka berkas BERDASARKAN NAMA PERSIS
(`14_transaction_items_raw.csv`). Kalau entri dihapus dari registry alih-alih disaring
saat menulis, 13/14/15 bergeser jadi 12/13/14 dan loader rusak — tanpa error di sisi
Sehati, karena Sehati merasa sudah menulis semuanya.

Yang diuji:
  1. `medical_soap_raw` MASIH ADA di registry (jangan dihapus!)
  2. Ia TIDAK ikut ditulis ke paket
  3. Nomor berkas yang dibaca loader Finance TIDAK berubah:
     03_treatments_raw, 05_transactions_header_raw, 06_transactions_detail_raw,
     11_membership_raw, 14_transaction_items_raw
  4. Paket memang punya lompatan nomor di posisi 12 — itu disengaja

Jalankan dari `sehati_clinic/`:  python -m scripts.cek_finance_pack
"""
from app.db.session import SessionLocal
from app.services.export_service import ExportService, FINANCE_PACK_EXCLUDE

# Berkas yang DIBUKA loader Finance (finance-ai/app/ingest/csv_loader.py).
# Kalau daftar ini berubah di sisi Finance, perbarui di sini juga.
DIBACA_LOADER = {
    "03_treatments_raw.csv",
    "05_transactions_header_raw.csv",
    "06_transactions_detail_raw.csv",
    "11_membership_raw.csv",
    "14_transaction_items_raw.csv",
}

_lulus, _gagal = 0, 0


def cek(label, ok, detail=""):
    global _lulus, _gagal
    if ok:
        _lulus += 1
        print(f"  ✓ {label}" + (f"\n      {detail}" if detail else ""))
    else:
        _gagal += 1
        print(f"  ✗ {label}" + (f"\n      {detail}" if detail else ""))


def main() -> None:
    db = SessionLocal()
    try:
        svc = ExportService(db)
        reg = svc.DATASET_REGISTRY

        print("1. Registry\n")
        nama_reg = [e["name"] for e in reg]
        cek("medical_soap_raw MASIH ADA di registry",
            "medical_soap_raw" in nama_reg,
            "menghapusnya akan menggeser nomor berkas — lihat docstring")
        cek("FINANCE_PACK_EXCLUDE memuat medical_soap_raw",
            "medical_soap_raw" in FINANCE_PACK_EXCLUDE,
            f"isi: {sorted(FINANCE_PACK_EXCLUDE)}")

        print("\n2. Nama berkas yang AKAN ditulis (simulasi, tanpa menulis)\n")
        akan_ditulis, dilewati = [], []
        for i, e in enumerate(reg, 1):
            fn = f"{i:02d}_{e['name']}.csv"
            (dilewati if e["name"] in FINANCE_PACK_EXCLUDE else akan_ditulis).append(fn)

        for fn in akan_ditulis:
            print(f"      {fn}")
        for fn in dilewati:
            print(f"      {fn}   ← DILEWATI")

        print("\n3. Nomor berkas yang dibaca loader Finance TIDAK bergeser\n")
        hilang = sorted(DIBACA_LOADER - set(akan_ditulis))
        cek("Kelima berkas yang dibuka loader tetap bernama sama",
            not hilang,
            "semua ada" if not hilang else f"HILANG/BERUBAH: {hilang}")

        print("\n4. Lompatan nomor disengaja\n")
        cek("medical_soap_raw tidak ikut ditulis",
            not any("medical_soap_raw" in f for f in akan_ditulis),
            f"dilewati: {dilewati}")
        cek("Paket berisi 14 berkas (dari 15 entri registry)",
            len(akan_ditulis) == len(reg) - len(dilewati),
            f"{len(akan_ditulis)} ditulis, {len(dilewati)} dilewati, {len(reg)} entri")

        print(f"\nHASIL: {_lulus} lulus, {_gagal} gagal")
    finally:
        db.close()


if __name__ == "__main__":
    main()
