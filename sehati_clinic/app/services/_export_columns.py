"""
Sehati Clinic Export — Schema Metadata per Dataset (C2.4)

Sumber-of-truth untuk:
- /web/export/dictionary.json
- /web/export/dictionary.md
- DATA_DICTIONARY.md di setiap ZIP pack
- Project_Memory/RawDataExport/01_DATA_DICTIONARY.md (regen via script)

Struktur per dataset:
    source_tables       : list tabel DB yang di-JOIN
    filter              : keterangan filter date range
    mask_pii_affects    : list nama kolom yang berubah saat mask_pii=True
    columns             : list of {name, type, description}

Types convention:
    int, float, str, date, datetime, bool, dict (JSON)
    Suffix " | null" kalau nullable.
"""


COLUMNS_METADATA: dict[str, dict] = {

    # =========================================================================
    "daily_operational_summary": {
        "source_tables": [
            "kunjungan", "pasien", "pemeriksaan_klinis",
            "kunjungan_tindakan", "transaksi_kasir", "kunjungan_resep",
        ],
        "filter": "tanggal range (per source pakai field tgl_*/waktu_* masing-masing)",
        "mask_pii_affects": [],
        "columns": [
            {"name": "tanggal", "type": "date", "description": "Hari yang di-rekap (ISO YYYY-MM-DD). Include hari kosong dengan nilai 0 untuk distribusi lengkap."},
            {"name": "jumlah_kunjungan", "type": "int", "description": "Count kunjungan dengan tgl_kunjungan di tanggal ini."},
            {"name": "jumlah_pasien_baru", "type": "int", "description": "Count pasien baru di-create di tanggal ini (filter pasien.created_at)."},
            {"name": "jumlah_konsul_dokter", "type": "int", "description": "Count pemeriksaan_klinis (SOAP) di kunjungan tanggal ini."},
            {"name": "jumlah_tindakan_selesai", "type": "int", "description": "Count kunjungan_tindakan status=SELESAI dengan waktu_selesai di tanggal ini."},
            {"name": "jumlah_transaksi", "type": "int", "description": "Count transaksi_kasir dengan waktu_bayar di tanggal ini."},
            {"name": "total_omzet", "type": "float", "description": "Sum total_tagihan transaksi_kasir di tanggal ini (Rp)."},
            {"name": "total_diskon", "type": "float", "description": "Sum nominal_diskon transaksi_kasir di tanggal ini (Rp)."},
            {"name": "jumlah_resep_dibayar", "type": "int", "description": "Count kunjungan_resep status=DIBAYAR di kunjungan tanggal ini."},
        ],
    },

    # =========================================================================
    "visits_raw": {
        "source_tables": ["kunjungan", "pasien", "master_staf"],
        "filter": "kunjungan.tgl_kunjungan range",
        "mask_pii_affects": ["nama_pasien"],
        "columns": [
            {"name": "id_kunjungan", "type": "int", "description": "Primary key kunjungan."},
            {"name": "tgl_kunjungan", "type": "datetime", "description": "Waktu kunjungan."},
            {"name": "id_pasien", "type": "int", "description": "FK ke pasien.id_pasien."},
            {"name": "no_rm", "type": "str", "description": "Nomor RM pasien (unique per pasien)."},
            {"name": "nama_pasien", "type": "str", "description": "Nama lengkap pasien. Mask-able via mask_pii → 'PASIEN_HASH_xxxxxxxx'."},
            {"name": "status_antrian", "type": "str", "description": "Status sekarang (ANTRI_KONSULTASI/KONSULTASI/.../COMPLETED/BATAL)."},
            {"name": "sumber_pendaftaran", "type": "str", "description": "Kolom teks bebas. Nilai live sistem: WALK_IN, MEMBERSHIP_ONLY. CATATAN: beberapa baris legacy/test berisi kode angka (mis. '1') tanpa legend otoritatif — perlakukan UNKNOWN, jangan dimap. Lihat section Catatan Anomali Data."},
            {"name": "keluhan_utama", "type": "str | null", "description": "Keluhan input FO saat daftar (text)."},
            {"name": "id_staf_fo", "type": "int | null", "description": "FK FO yang daftar."},
            {"name": "nama_fo", "type": "str | null", "description": "Nama staff FO (nullable kalau staf hilang)."},
            {"name": "created_at", "type": "datetime", "description": "Timestamp record di-insert."},
        ],
    },

    # =========================================================================
    "treatments_raw": {
        "source_tables": ["kunjungan_tindakan", "master_treatment", "master_staf", "kunjungan"],
        "filter": "kunjungan.tgl_kunjungan range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_kunjungan_tindakan", "type": "int", "description": "Primary key kunjungan_tindakan."},
            {"name": "id_kunjungan", "type": "int", "description": "FK ke kunjungan."},
            {"name": "tgl_kunjungan", "type": "datetime", "description": "Waktu kunjungan (dari kunjungan)."},
            {"name": "id_pasien", "type": "int", "description": "FK ke pasien (denormalized via kunjungan)."},
            {"name": "id_treatment", "type": "int", "description": "FK ke master_treatment."},
            {"name": "nama_treatment", "type": "str", "description": "Nama treatment dari master."},
            {"name": "role_pelaksana", "type": "str", "description": "Role yang boleh laksanakan (Dokter/Perawat/dll)."},
            {"name": "harga_master", "type": "float", "description": "Harga di master_treatment.harga (Rp). Pre-diskon."},
            {"name": "status_tindakan", "type": "str", "description": "PENDING / PROSES / SELESAI."},
            {"name": "id_staf_pelaksana", "type": "int | null", "description": "FK staff yang execute tindakan."},
            {"name": "nama_pelaksana", "type": "str | null", "description": "Nama staff pelaksana."},
            {"name": "waktu_mulai", "type": "datetime | null", "description": "Waktu start tindakan."},
            {"name": "waktu_selesai", "type": "datetime | null", "description": "Waktu end tindakan."},
            {"name": "durasi_aktual_menit", "type": "int | null", "description": "Computed: (waktu_selesai − waktu_mulai) dalam menit."},
        ],
    },

    # =========================================================================
    "products_prescription_sales_raw": {
        "source_tables": ["kunjungan_resep", "master_produk", "kunjungan"],
        "filter": "kunjungan.tgl_kunjungan range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_resep", "type": "int", "description": "Primary key kunjungan_resep."},
            {"name": "id_kunjungan", "type": "int", "description": "FK ke kunjungan."},
            {"name": "tgl_kunjungan", "type": "datetime", "description": "Waktu kunjungan."},
            {"name": "id_pasien", "type": "int", "description": "FK pasien (denormalized via kunjungan)."},
            {"name": "id_produk", "type": "int", "description": "FK ke master_produk."},
            {"name": "kode_produk", "type": "str", "description": "Kode produk (e.g., 'KM01', 'AUTO-0042')."},
            {"name": "nama_produk", "type": "str", "description": "Nama produk dari master."},
            {"name": "tipe_produk", "type": "str", "description": "RETAIL / CABIN / ALAT (tipe master_produk)."},
            {"name": "harga_satuan_master", "type": "float", "description": "Harga jual per unit dari master (Rp). Pre-diskon."},
            {"name": "qty", "type": "float", "description": "Qty diresepkan (pcs/tablet/dll, sesuai satuan master)."},
            {"name": "subtotal_estimasi", "type": "float", "description": "Computed: qty × harga_satuan_master (Rp). Estimasi pre-diskon."},
            {"name": "aturan_pakai", "type": "str | null", "description": "Instruksi pemakaian (e.g., '3×1 setelah makan')."},
            {"name": "status_item", "type": "str", "description": "PENDING / BATAL / DIBAYAR."},
            {"name": "id_staf_input", "type": "int", "description": "FK staff yang input resep (Dokter/FO)."},
        ],
    },

    # =========================================================================
    "transactions_header_raw": {
        "source_tables": ["transaksi_kasir", "kunjungan", "pasien", "master_staf"],
        "filter": "transaksi_kasir.waktu_bayar range",
        "mask_pii_affects": ["nama_pasien"],
        "columns": [
            {"name": "id_transaksi", "type": "int", "description": "Primary key transaksi_kasir."},
            {"name": "id_kunjungan", "type": "int | null", "description": "FK ke kunjungan."},
            {"name": "id_pasien", "type": "int | null", "description": "FK pasien (denormalized via kunjungan)."},
            {"name": "no_rm", "type": "str | null", "description": "Nomor RM pasien."},
            {"name": "nama_pasien", "type": "str | null", "description": "Nama pasien. Mask-able via mask_pii."},
            {"name": "waktu_bayar", "type": "datetime | null", "description": "Timestamp pembayaran selesai."},
            {"name": "id_staf_kasir", "type": "int | null", "description": "FK kasir yang handle transaksi."},
            {"name": "nama_kasir", "type": "str | null", "description": "Nama kasir."},
            {"name": "subtotal", "type": "float", "description": "Subtotal sebelum diskon (Rp)."},
            {"name": "nominal_diskon", "type": "float", "description": "Diskon yang diberi (Rp)."},
            {"name": "total_tagihan", "type": "float", "description": "Total final yang dibayar (Rp) = subtotal − diskon."},
            {"name": "keterangan_promo", "type": "str | null", "description": "Catatan promo/diskon (e.g., 'Member VIP 10%')."},
            {"name": "status_transaksi", "type": "str", "description": "BAYAR (sah) atau VOID (dibatalkan). PENTING: untuk omzet filter status='BAYAR'; VOID JANGAN dihitung sebagai penjualan."},
            {"name": "doc_number", "type": "str | null", "description": "Nomor dokumen stabil TRX-YYYY-MM-###### (referensi jurnal Finance, M-FIN-1). Backfill dari id_transaksi untuk baris lama."},
            {"name": "updated_at", "type": "datetime | null", "description": "Timestamp update terakhir (auto-bump). Untuk sync incremental Finance (tangkap void/koreksi)."},
            {"name": "dpp", "type": "float | null", "description": "Dasar Pengenaan Pajak (Rp). DORMANT — NULL/0 untuk non-PKP. M-FIN-4."},
            {"name": "ppn", "type": "float", "description": "PPN keluaran (Rp). 0 untuk non-PKP (KLN). Aktif saat PKP."},
            {"name": "is_kena_ppn", "type": "bool", "description": "True bila transaksi kena PPN. False untuk non-PKP."},
            {"name": "kode_entitas", "type": "str", "description": "Penanda PT pemilik transaksi. Konstan 'KLN' (1 instance Sehati = Klinik JoDerma). Disiapkan untuk multi-PT."},
        ],
    },

    # =========================================================================
    "transactions_detail_raw": {
        "source_tables": ["transaksi_pembayaran", "transaksi_kasir"],
        "filter": "transaksi_kasir.waktu_bayar range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_pembayaran", "type": "int", "description": "Primary key transaksi_pembayaran."},
            {"name": "id_transaksi", "type": "int", "description": "FK ke transaksi_kasir (parent)."},
            {"name": "waktu_bayar", "type": "datetime | null", "description": "Timestamp dari transaksi_kasir parent (denormalized)."},
            {"name": "metode_bayar", "type": "str", "description": "Kolom teks bebas. Nilai live sistem (dropdown kasir): TUNAI, QRIS, DEBIT, KREDIT, TRANSFER. Import historical pakai label CASH (= TUNAI). Beberapa baris test paling awal (id_transaksi 1-7) berisi kode angka 1/2/4 tanpa legend — perlakukan UNKNOWN. Lihat section Catatan Anomali Data."},
            {"name": "nominal", "type": "float", "description": "Nominal yang dibayar via metode ini (Rp). Split payment ready."},
            {"name": "status_transaksi", "type": "str", "description": "BAYAR (sah) atau VOID (dibatalkan). PENTING: untuk omzet filter status='BAYAR'; VOID JANGAN dihitung sebagai penjualan."},
            {"name": "tgl_settle", "type": "date | null", "description": "Tanggal settlement EDC/QRIS ke bank (T+1). NULL = tunai/langsung. M-FIN-4 G12."},
        ],
    },

    # =========================================================================
    "transaction_items_raw": {
        "source_tables": ["transaksi_detail_produk", "transaksi_detail_tindakan", "master_produk", "master_treatment", "transaksi_kasir"],
        "filter": "transaksi_kasir.waktu_bayar range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_transaksi", "type": "int", "description": "FK ke transaksi_kasir."},
            {"name": "doc_number", "type": "str | null", "description": "Nomor dokumen transaksi (TRX-...)."},
            {"name": "waktu_bayar", "type": "datetime | null", "description": "Timestamp pembayaran (dari transaksi_kasir)."},
            {"name": "jenis_item", "type": "str", "description": "PRODUK atau TREATMENT."},
            {"name": "id_item", "type": "int", "description": "id_produk (PRODUK) atau id_treatment (TREATMENT)."},
            {"name": "nama_item", "type": "str", "description": "Nama produk/treatment dari master."},
            {"name": "qty", "type": "float", "description": "Kuantitas item."},
            {"name": "harga_satuan", "type": "float", "description": "Harga jual per unit saat transaksi (Rp)."},
            {"name": "diskon_item", "type": "float", "description": "Alokasi diskon ke item ini (Rp)."},
            {"name": "subtotal", "type": "float", "description": "Subtotal item (Rp)."},
            {"name": "hpp_satuan", "type": "float | null", "description": "Snapshot COGS per unit: HPP produk / BHP treatment (Rp)."},
            {"name": "kode_entitas", "type": "str", "description": "Penanda PT. Konstan 'KLN'."},
        ],
    },

    # =========================================================================
    "refunds_raw": {
        "source_tables": ["transaksi_refund", "transaksi_kasir", "master_staf"],
        "filter": "transaksi_refund.tgl_refund range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_refund", "type": "int", "description": "Primary key transaksi_refund."},
            {"name": "id_transaksi", "type": "int | null", "description": "Transaksi asal yang di-refund."},
            {"name": "doc_number_asal", "type": "str | null", "description": "doc_number transaksi asal (TRX-...)."},
            {"name": "doc_number_refund", "type": "str | null", "description": "Nomor dokumen refund (RFN-...)."},
            {"name": "tgl_refund", "type": "datetime | null", "description": "Waktu refund."},
            {"name": "nilai_refund", "type": "float", "description": "Nilai yang dikembalikan (Rp). Bisa sebagian."},
            {"name": "metode_refund", "type": "str | null", "description": "Metode pengembalian (TUNAI/TRANSFER/dll)."},
            {"name": "alasan", "type": "str | null", "description": "Alasan refund."},
            {"name": "id_staf_refund", "type": "int | null", "description": "Staf yang memproses refund."},
            {"name": "nama_staf", "type": "str | null", "description": "Nama staf refund."},
            {"name": "jenis_refund", "type": "str", "description": "ITEM = satu baris resep/racikan dibatalkan; TRANSAKSI = seluruh transaksi."},
            {"name": "id_resep", "type": "int | null", "description": "Baris kunjungan_resep yang direfund (jenis_refund=ITEM)."},
            {"name": "id_kunjungan_racikan", "type": "int | null", "description": "Racikan yang direfund (jenis_refund=ITEM). Racikan all-or-nothing."},
            {"name": "kode_entitas", "type": "str", "description": "Penanda PT. Konstan 'KLN'."},
        ],
        "catatan": (
            "Refund per item (task #54-F, 2026-09-22) MENGURANGI "
            "transaksi_kasir.total_tagihan, jadi omzet di laporan lain sudah bersih "
            "dari nilai ini — JANGAN dikurangkan dua kali saat menyusun jurnal."
        ),
    },

    # =========================================================================
    "inventory_movements_raw": {
        "source_tables": ["inventory_history", "master_produk", "inventory_stok", "master_staf"],
        "filter": "inventory_history.waktu_mutasi range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_history", "type": "int", "description": "Primary key inventory_history."},
            {"name": "waktu_mutasi", "type": "datetime", "description": "Timestamp mutasi terjadi."},
            {"name": "tipe_item", "type": "str", "description": "PRODUK atau BAHAN (polymorphic). Determinant untuk id_produk vs id_bahan."},
            {"name": "id_produk", "type": "int | null", "description": "FK master_produk. XOR dengan id_bahan."},
            {"name": "nama_produk", "type": "str | null", "description": "Nama produk (kalau tipe_item=PRODUK)."},
            {"name": "id_bahan", "type": "int | null", "description": "FK inventory_stok. XOR dengan id_produk."},
            {"name": "nama_bahan", "type": "str | null", "description": "Nama bahan (kalau tipe_item=BAHAN)."},
            {"name": "jenis_mutasi", "type": "str", "description": "PEMBELIAN / TINDAKAN / PENJUALAN / PENYESUAIAN / WRITE_OFF / RETUR."},
            {"name": "qty_perubahan", "type": "float", "description": "Delta stok. Negatif = keluar, positif = masuk."},
            {"name": "stok_akhir", "type": "float", "description": "Snapshot stok setelah mutasi (cumulative)."},
            {"name": "id_staf", "type": "int | null", "description": "FK staff yang trigger mutasi."},
            {"name": "nama_staf", "type": "str | null", "description": "Nama staff actor."},
            {"name": "referensi", "type": "str | null", "description": "Reference link (e.g., 'Tindakan ID-123', 'PO-260605-001')."},
            {"name": "keterangan", "type": "str | null", "description": "Catatan bebas tentang mutasi."},
            {"name": "hpp_satuan", "type": "float | null", "description": "Snapshot cost per unit saat mutasi (produk HPP / bahan harga_modal). M-FIN-3."},
            {"name": "nilai_mutasi", "type": "float | null", "description": "Nilai mutasi = qty_perubahan x hpp_satuan (Rp). Menilai PENYESUAIAN/WRITE_OFF/RETUR."},
        ],
    },

    # =========================================================================
    "purchasing_orders_header_raw": {
        "source_tables": ["pemesanan", "master_staf"],
        "filter": "pemesanan.created_at range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_pemesanan", "type": "int", "description": "Primary key pemesanan (PO)."},
            {"name": "nomor_po", "type": "str", "description": "Nomor PO format 'PO-YYMMDD-NNN'. Unique."},
            {"name": "tgl_pemesanan", "type": "datetime", "description": "Waktu PO di-create."},
            {"name": "supplier_nama", "type": "str | null", "description": "Nama supplier (free text)."},
            {"name": "tgl_perkiraan_datang", "type": "date | null", "description": "Estimasi barang tiba."},
            {"name": "status", "type": "str", "description": "SUBMITTED / ORDERED / PARTIAL_RECEIVED / RECEIVED / CANCELLED."},
            {"name": "id_staf_pemesan", "type": "int | null", "description": "FK staff yang create PO."},
            {"name": "nama_pemesan", "type": "str | null", "description": "Nama pemesan."},
            {"name": "total_estimasi_biaya", "type": "float", "description": "Total estimasi biaya (sum item subtotal) (Rp)."},
            {"name": "catatan", "type": "str | null", "description": "Catatan bebas PO."},
            {"name": "created_at", "type": "datetime | null", "description": "Timestamp record insert."},
            {"name": "updated_at", "type": "datetime | null", "description": "Timestamp record last update."},
        ],
    },

    # =========================================================================
    "purchasing_orders_item_raw": {
        "source_tables": ["pemesanan_item", "pemesanan"],
        "filter": "pemesanan.created_at range (JOIN to parent)",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_item", "type": "int", "description": "Primary key pemesanan_item."},
            {"name": "id_pemesanan", "type": "int", "description": "FK parent pemesanan."},
            {"name": "nomor_po", "type": "str", "description": "Nomor PO (denormalized untuk easy JOIN)."},
            {"name": "tipe_item", "type": "str", "description": "PRODUK atau BAHAN (polymorphic, XOR)."},
            {"name": "id_produk", "type": "int | null", "description": "FK master_produk kalau tipe_item=PRODUK."},
            {"name": "id_bahan", "type": "int | null", "description": "FK inventory_stok kalau tipe_item=BAHAN."},
            {"name": "nama_snapshot", "type": "str", "description": "Nama item snapshot saat PO di-create (resilient terhadap rename master)."},
            {"name": "satuan_snapshot", "type": "str | null", "description": "Satuan snapshot saat PO."},
            {"name": "qty_dipesan", "type": "float", "description": "Qty yang dipesan."},
            {"name": "qty_diterima", "type": "float", "description": "Qty yang sudah diterima (akumulasi receive events). 0 ≤ qty_diterima ≤ qty_dipesan."},
            {"name": "harga_satuan", "type": "float", "description": "Harga per unit (Rp). Bisa NULL kalau belum dikonfirmasi supplier."},
            {"name": "subtotal", "type": "float", "description": "qty_dipesan × harga_satuan (Rp)."},
            {"name": "catatan_item", "type": "str | null", "description": "Catatan item-level."},
        ],
    },

    # =========================================================================
    "purchasing_orders_receive_raw": {
        "source_tables": ["pemesanan_receive", "pemesanan", "master_staf"],
        "filter": "pemesanan_receive.tgl_terima range",
        "mask_pii_affects": [],
        "columns": [
            {"name": "id_receive", "type": "int", "description": "Primary key pemesanan_receive (event log)."},
            {"name": "id_pemesanan_item", "type": "int", "description": "FK ke pemesanan_item (item yang di-receive)."},
            {"name": "id_pemesanan", "type": "int", "description": "FK parent pemesanan (denormalized)."},
            {"name": "nomor_po", "type": "str", "description": "Nomor PO (denormalized untuk easy JOIN)."},
            {"name": "qty_diterima_event", "type": "float", "description": "Qty diterima di event ini (partial receive ready)."},
            {"name": "tgl_terima", "type": "datetime", "description": "Waktu receive event."},
            {"name": "id_staf_penerima", "type": "int | null", "description": "FK staff yang receive."},
            {"name": "nama_receiver", "type": "str | null", "description": "Nama receiver."},
            {"name": "nomor_faktur", "type": "str | null", "description": "Nomor faktur supplier (kalau ada)."},
            {"name": "catatan", "type": "str | null", "description": "Catatan event receive."},
        ],
    },

    # =========================================================================
    "membership_raw": {
        "source_tables": ["pasien_membership_history", "master_membership", "pasien", "master_staf"],
        "filter": "pasien_membership_history.created_at range",
        "mask_pii_affects": ["nama_pasien"],
        "columns": [
            {"name": "id_history", "type": "int", "description": "Primary key pasien_membership_history."},
            {"name": "id_pasien", "type": "int", "description": "FK pasien."},
            {"name": "no_rm", "type": "str", "description": "Nomor RM pasien."},
            {"name": "nama_pasien", "type": "str", "description": "Nama pasien. Mask-able."},
            {"name": "id_membership", "type": "int", "description": "FK master_membership (tier)."},
            {"name": "nama_tier", "type": "str", "description": "Nama tier (e.g., 'VIP', 'VVIP')."},
            {"name": "tgl_aktif", "type": "date", "description": "Tanggal mulai aktif membership."},
            {"name": "tgl_expired", "type": "date", "description": "Tanggal expired."},
            {"name": "harga_bayar", "type": "float", "description": "Harga yang dibayar pasien untuk aktivasi (Rp)."},
            {"name": "is_active", "type": "bool", "description": "Status aktif/expired sekarang (computed via tgl_expired vs today)."},
            {"name": "id_staf_aktivasi", "type": "int | null", "description": "FK staff yang aktivasi."},
            {"name": "nama_aktivator", "type": "str | null", "description": "Nama staff yang aktivasi."},
            {"name": "id_transaksi_aktivasi", "type": "int | null", "description": "FK transaksi_kasir untuk pembayaran aktivasi."},
            {"name": "created_at", "type": "datetime | null", "description": "Timestamp record insert."},
        ],
    },

    # =========================================================================
    "medical_soap_raw": {
        "source_tables": ["pemeriksaan_klinis", "kunjungan", "master_staf"],
        "filter": "kunjungan.tgl_kunjungan range",
        "mask_pii_affects": ["nama_dokter"],
        "columns": [
            {"name": "id_pemeriksaan", "type": "int", "description": "Primary key pemeriksaan_klinis."},
            {"name": "id_kunjungan", "type": "int", "description": "FK kunjungan."},
            {"name": "tgl_kunjungan", "type": "datetime", "description": "Waktu kunjungan (dari kunjungan)."},
            {"name": "id_pasien", "type": "int | null", "description": "FK pasien."},
            {"name": "id_staf_dokter", "type": "int | null", "description": "FK dokter yang konsul."},
            {"name": "nama_dokter", "type": "str | null", "description": "Nama dokter. Mask-able via mask_pii → 'DOKTER_HASH_xxxxxxxx'."},
            {"name": "anamnesa", "type": "str | null", "description": "S - Subjective (free text). PII risk: dokter mungkin tulis nama pasien di sini."},
            {"name": "pemeriksaan_fisik", "type": "str | null", "description": "O - Objective (free text)."},
            {"name": "diagnosa", "type": "str | null", "description": "A - Assessment (diagnosis)."},
            {"name": "saran_treatment", "type": "str | null", "description": "P partial — catatan dokter untuk perawat saat eksekusi."},
            {"name": "saran_produk", "type": "str | null", "description": "P partial — instruksi tambahan untuk pasien saat pakai produk."},
        ],
    },

    # =========================================================================
    "staff_activity_raw": {
        "source_tables": ["audit_log", "master_staf"],
        "filter": "audit_log.waktu range",
        "mask_pii_affects": ["data_lama", "data_baru"],
        "columns": [
            {"name": "id_log", "type": "int", "description": "Primary key audit_log."},
            {"name": "waktu", "type": "datetime", "description": "Timestamp event terjadi."},
            {"name": "id_staf", "type": "int | null", "description": "FK staff yang trigger event. NULL untuk LOGIN_FAIL pre-auth."},
            {"name": "nama_staf", "type": "str | null", "description": "Nama staff."},
            {"name": "role_staf", "type": "str | null", "description": "Role staff (OWNER/SUPERADMIN/.../FO)."},
            {"name": "aksi", "type": "str", "description": "Action type (CREATE/UPDATE/DELETE/LOGIN_SUCCESS/LOGIN_FAIL/PO_CANCEL/EXPORT_PACK/EXPORT_DATASET/dll)."},
            {"name": "tabel_target", "type": "str | null", "description": "Tabel yang di-affect (pasien/kunjungan/pemesanan/dll)."},
            {"name": "id_target", "type": "int | null", "description": "ID record target di tabel_target."},
            {"name": "status_aksi", "type": "str", "description": "SUCCESS atau FAILED."},
            {"name": "keterangan", "type": "str | null", "description": "Detail event (free text)."},
            {"name": "status_lama", "type": "str | null", "description": "Status_antrian SEBELUM (diparse dari data_lama). Untuk rekonstruksi transisi/dwell-time. PII-free."},
            {"name": "status_baru", "type": "str | null", "description": "Status_antrian SESUDAH (diparse dari data_baru). Inti untuk timeline transisi. PII-free."},
            {"name": "data_lama", "type": "json | null", "description": "Snapshot payload sebelum (bisa berisi PII pada event pasien). NULL saat mask_pii."},
            {"name": "data_baru", "type": "json | null", "description": "Snapshot payload sesudah (bisa berisi PII pada event pasien). NULL saat mask_pii."},
        ],
    },
}


__all__ = ["COLUMNS_METADATA"]
