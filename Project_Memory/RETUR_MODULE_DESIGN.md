# Design Doc — Modul Retur Produk (mendekati ED)

**Tanggal:** 2026-07-03
**Status:** DRAFT desain — belum kode. Dari permintaan apotek (dr. Hansen).
**Tujuan:** retur produk yang mendekati expired ke distributor, dengan jejak batch/lot yang jelas.

---

## 1. Alur (versi dr. Hansen)

1. Apoteker **buat form retur** → **cetak** → kirim ke distributor.
2. Distributor **approve** → apoteker **kirim barang retur** → **OTOMATIS batch/lot produk itu berkurang**
   (potong `stok_lot.qty_sisa` batch yang diretur).
3. Apoteker **buat nota retur** (isi TBD).
4. **PERCABANGAN:**
   - **(A) Retur DENGAN pengembalian uang** → nota retur SELESAI → kirim ke finance.
   - **(B) Retur TANPA uang (tukar barang)** → apoteker **input barang pengganti** (batch, ED, jumlah)
     → produk pengganti **masuk lot** (mini-receive).

---

## 2. Prinsip desain (usulan)

- **Pilih batch/lot MANUAL** untuk diretur (bukan FEFO otomatis) — retur menyasar batch mendekati ED spesifik;
  manual = jejak QC jelas (konsisten dgn filosofi void-return P-L6b, DEC).
- Retur = pengurangan lot BER-ALASAN "RETUR" (beda dari write-off "EXPIRED/RUSAK"; retur bisa balik uang/barang).
- Status retur: DRAFT → (cetak/kirim) → APPROVED (distributor setuju, ditandai apoteker) → SELESAI.
  Barang baru dipotong dari lot saat status "kirim barang" (setelah approved), bukan saat draft.
- Branch B (tukar barang) = setelah potong lot lama, buat lot baru dari input batch/ED/qty (pakai ulang
  mekanisme receive/lot P-L4/P-L5).

---

## 3. Model data (sketsa)

- `retur_produk` (header): id, nomor_retur, id_distributor, tgl, status, jenis (REFUND / TUKAR_BARANG),
  id_staf_apoteker, alasan, total_nilai (utk refund), catatan.
- `retur_produk_item`: id_retur, id_produk, **id_lot** (batch diretur), batch_no/tgl_ed snapshot, qty,
  harga (utk nilai refund), + (branch B) data lot pengganti (batch/ED/qty baru).

---

## 4. Keputusan TERBUKA (perlu dr. Hansen)

1. **Isi NOTA RETUR** — field apa saja? (nomor, tgl, distributor, item+batch+ED+qty, nilai, jenis refund/tukar,
   ttd?). Perlu dr. Hansen sebutkan seperti form fisiknya.
2. **Approval distributor**: cukup apoteker menandai "sudah di-approve distributor" manual (tanpa integrasi),
   atau perlu upload bukti? (usul: tandai manual + catatan.)
3. **Kapan lot dipotong**: saat "kirim barang retur" (setelah approved) — konfirmasi.
4. **Nilai refund (branch A)**: pakai harga_terima lot? harga khusus dari distributor? (usul: default harga_terima
   lot, bisa override.)
5. **Branch B (tukar)**: barang pengganti = produk SAMA (batch baru) atau bisa produk lain? (usul: sama; kalau
   beda = kasus khusus.)
6. **Cetak**: 1 cetakan (form retur untuk distributor) + nota retur (arsip/finance)? Sama seperti faktur 2-print?

---

## 5. Fase (usulan, setelah faktur FK)
- RT-L1 model retur + migrasi.
- RT-L2 form retur + pilih batch/lot manual + cetak form retur.
- RT-L3 proses "kirim barang" → potong lot (alasan RETUR) + nota retur.
- RT-L4 branch A (refund → finance) / branch B (tukar → input lot pengganti).
- RT-L5 test + housekeeping.

## 6. Blind spots
- Retur menyentuh lot → konsistensi cache stok_terkini (recompute = Σ qty_sisa, seperti opname/write-off).
- Jangan bentrok dengan write-off: retur = ke distributor (recover), write-off = buang. Beda alasan mutasi.
- Branch B = 2 mutasi (keluar lot lama + masuk lot baru) dalam 1 transaksi — hati-hati atomic.

---

## 7. KEPUTUSAN TERKUNCI (dr. Hansen, 2026-07-03)

- **Approval distributor:** apoteker tandai MANUAL "sudah di-approve" + catatan (tanpa integrasi). [confirmed]
- **Lot dipotong:** saat "kirim barang retur" (SETELAH approved), bukan draft. [confirmed]
- **2 cetakan:** (a) **Form Retur** → distributor (minta persetujuan), (b) **Nota Retur** → arsip/finance
  (setelah barang dikirim). Pola mirip faktur 2-cetak. [confirmed]
- **Pilih batch/lot MANUAL** (bukan FEFO) — jejak QC. Alasan mutasi = "RETUR" (beda write-off). [confirmed]
- **Nilai refund (branch A):** default `harga_terima` lot batch yang diretur, **bisa di-override**. [confirmed]
- **Barang pengganti (branch B):** **produk SAMA**, hanya batch/ED baru (mini-receive lot). Produk lain =
  di luar cakupan. [confirmed]

**Status enum retur (usul):** DRAFT → APPROVED → SELESAI (+ CANCELLED opsional). Baru potong lot di APPROVED→kirim.
**Jenis retur:** REFUND / TUKAR_BARANG (dipilih saat buat / saat selesai).

**MASIH DIBUTUHKAN sebelum RT-L1:** daftar **field NOTA RETUR** + **FORM RETUR** dari dr. Hansen (seperti
form fisiknya) — mengikuti gaya waktu menyebut kolom faktur. Setelah itu fase RT-L1..L5 siap dieksekusi.

**Fase:** RT-L1 model+migrasi · RT-L2 form retur + pilih batch manual + cetak Form Retur ·
RT-L3 "kirim barang" → potong lot (recompute cache stok_terkini) + Nota Retur ·
RT-L4 branch A (refund→finance) / branch B (tukar→lot pengganti) · RT-L5 test + housekeeping.

---

## 8. SPESIFIKASI FINAL (dr. Hansen, 2026-07-03) — REVISI ALUR

**Perubahan penting: APPROVAL = potong lot (unified).** Tak ada langkah "kirim barang" terpisah.
Saat form retur di-approve → OTOMATIS potong `stok_lot.qty_sisa` sesuai batch + qty di form (recompute
cache stok_terkini). Alasan mutasi "RETUR".

**RBAC approval retur (luas):** OWNER, SUPERADMIN, PURCHASING, **APOTEKER** (apoteker boleh approve sendiri).

**FORM RETUR (permintaan → dikirim ke distributor):**
- Header: **nomor permintaan retur**, tanggal, distributor, **alasan (form-level, 1 saja)**.
- Per item: nama, **batch**, **ED**, **qty**. (+ alasan per-item OPSIONAL — untuk kasus beda per item.)
- Cetak Form Retur untuk distributor.

**NOTA RETUR (respon distributor — diterima & diinput apoteker):**
- Field nota: **nomor nota**, **tanggal penerimaan** (barang/uang), per item: nama, qty, batch, ED, harga satuan.
- 2 jenis penyelesaian:
  - **(B) TUKAR BARANG:** apoteker input nota barang → tiap item (produk sama, batch/ED/qty/harga baru)
    → **MASUK LOT** (mini-receive). Menutup retur = SELESAI.
  - **(A) REFUND UANG:** dari sisi apotek TIDAK ada perubahan stok.
    → **DISKUSI (usul saya: TETAP diinput ringan)**: catat nomor nota + tgl + total nilai refund → untuk
      (1) bukti ke finance, (2) MENUTUP retur (kalau tidak, retur APPROVED yg stoknya sudah keluar akan
      MENGGANTUNG tanpa penyelesaian — sama seperti masalah PO menggantung), (3) laporan (nilai retur
      dipulihkan sebagai uang vs barang). TANPA input lot. Form refund = header nota saja.

**Model (refined):**
- `retur_produk` (header): id, nomor_retur, tgl, id_distributor, alasan, status (DRAFT/APPROVED/SELESAI/CANCELLED),
  jenis_penyelesaian (REFUND/TUKAR_BARANG, NULL sampai nota diinput), id_staf_pembuat, id_staf_approver,
  tgl_approve, nomor_nota, tgl_nota, total_nilai, catatan.
- `retur_produk_item`: id_retur, id_produk, id_lot, batch_no/tgl_ed snapshot, qty, harga_terima snapshot, alasan_item.
- Barang pengganti (branch B): buat StokLot baru (produk sama, batch/ED/qty/harga dari nota) + inventory_history
  alasan RETUR_TUKAR. (Traceability via nomor_retur di keterangan.)

**Fase:** RT-L1 model+migrasi · RT-L2 form retur + pilih lot manual + approve(=potong lot) + cetak Form Retur ·
RT-L3 input Nota Retur: branch B (masuk lot) / branch A (refund, tutup) + cetak Nota Retur · RT-L4 test+housekeeping.
