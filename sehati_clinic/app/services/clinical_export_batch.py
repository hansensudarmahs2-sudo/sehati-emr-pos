"""Penulis paket klinis — ZIP atomik + enkripsi age. Pola sama dengan finance.

MENGIKUTI POLA YANG SUDAH ADA, BUKAN MEMBUAT YANG BARU
------------------------------------------------------
Sama seperti `finance_export_batch`: satu ZIP + `manifest.json`, ditulis ATOMIK
(`.tmp` -> rename), jejak append-only di `export_log.jsonl`, sidik jari isi supaya
ekspor berulang bisa tahu "tidak ada perubahan". File-drop: Sehati MENULIS,
penerima memindai sendiri, Sehati tidak pernah dihubungi.

BEDA PENTING DARI finance
-------------------------
1. **Terenkripsi age** [keputusan dr. Hansen 2026-09-30]. Paket ini memuat SOAP
   dan teks bebas; ia setara backup database, bukan laporan keuangan. ZIP polos
   DIHAPUS setelah terenkripsi — bukan dibiarkan "untuk sementara".
   Kalau `age` atau `BACKUP_RECIPIENT` tidak ada, ekspor **GAGAL** alih-alih
   menulis polos diam-diam. Gagal terang-terangan lebih baik daripada berhasil
   dengan perlindungan yang hilang tanpa diberitahu.
2. **Folder drop TERPISAH** dari finance — hak akses & jalur keluar berbeda.
3. **Menulis ke DB** lebih dulu (`sinkron_pseudonim`), tidak seperti finance yang
   murni baca.

⚠ Folder drop TIDAK BOLEH berada di bawah folder repo atau folder tersinkron
  (Drive/OneDrive/Dropbox). Diperiksa saat jalan, bukan diasumsikan.
"""
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from datetime import date, datetime, timedelta, timezone

SCHEMA_VERSION = "1.0"
WIB = timezone(timedelta(hours=7))
LOG_NAME = "export_log.jsonl"


def envval(nama: str, default: str = "") -> str:
    """Ambil setelan dari os.environ, JATUH KEMBALI ke berkas `.env`.

    ⚠ KENAPA PERLU JATUH-KEMBALI INI (diperiksa, bukan diasumsikan):
      `pydantic-settings` di `app/config.py` memang membaca `.env`, tapi HANYA
      untuk field yang dideklarasikan di kelas `Settings` — ia tidak pernah
      mengisi `os.environ`. Jadi di DEV, `os.getenv("BACKUP_RECIPIENT")` kosong
      meskipun barisnya ADA di `.env`. Di MINI PC berhasil, karena
      docker-compose `env_file:` memang memasukkannya ke environ container.

      Beda perilaku antar mesin seperti itu paling menyesatkan: pesannya
      berbunyi "BACKUP_RECIPIENT tidak ada" padahal barisnya terlihat jelas.
      `deploy/backup.sh` sudah memakai pola grep-.env yang sama.
    """
    v = (os.getenv(nama) or "").strip()
    if v:
        return v
    env = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), ".env")
    try:
        with open(env, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{nama}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


DEFAULT_DROP = envval("SEHATI_CLINICAL_DROP", "/mnt/e/SehatiExport/clinical_pack")

# Nama folder yang menandakan tempat itu tersinkron ke cloud atau bagian repo.
# Paket klinis di sana = SOAP pasien ikut naik ke cloud tanpa ada yang menyadari.
POLA_TERLARANG = ("/.git/", "onedrive", "dropbox", "google drive", "gdrive",
                  "icloud", "sehati-emr-pos")


class DropTidakAmanError(RuntimeError):
    """Folder drop berada di tempat yang tersinkron/ter-git."""


class EnkripsiTidakTersediaError(RuntimeError):
    """age atau BACKUP_RECIPIENT tidak ada — paket klinis tidak boleh polos."""


def periksa_drop(out_dir: str) -> None:
    """Tolak folder drop yang tersinkron cloud atau di dalam repo."""
    p = os.path.abspath(out_dir).replace("\\", "/").lower()
    kena = [x for x in POLA_TERLARANG if x in p + "/"]
    if kena:
        raise DropTidakAmanError(
            f"Folder drop klinis '{out_dir}' mengandung {kena} — itu tempat "
            f"tersinkron cloud atau bagian repo git. Paket klinis memuat SOAP "
            f"pasien; ia tidak boleh berada di sana. Pindahkan lewat env "
            f"SEHATI_CLINICAL_DROP.")


def _recipient() -> str:
    r = envval("BACKUP_RECIPIENT")
    if not r:
        raise EnkripsiTidakTersediaError(
            "BACKUP_RECIPIENT (kunci publik age) tidak ada di environment "
            "maupun di sehati_clinic/.env. "
            "Paket klinis WAJIB terenkripsi — ekspor dibatalkan. Kunci yang sama "
            "dipakai backup; kunci privatnya ada di desktop, bukan di mini PC.")
    if shutil.which("age") is None:
        raise EnkripsiTidakTersediaError(
            "Program `age` tidak terpasang di mesin ini. Paket klinis WAJIB "
            "terenkripsi — ekspor dibatalkan. Pasang age lalu ulangi.")
    return r


# ---------------------------------------------------------------- fingerprint
def _fingerprint(datasets) -> str:
    """Sidik jari isi, MENGABAIKAN stamp/exported_at yang selalu berubah.

    Seluruh dataset dihitung — tidak ada yang dikecualikan seperti di finance
    (`FINGERPRINT_EXCLUDE` di sana untuk aktivitas login). Di paket klinis, SOAP
    yang berubah memang perubahan yang berarti.
    """
    joined = "\n".join(f"{d['name']}:{d['sha256']}"
                       for d in sorted(datasets, key=lambda x: x["name"]))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_datasets(db, tgl_dari: date | None, tgl_sampai: date | None):
    """Hitung dataset di memori. Return (meta, data_map, total, fp, info_pid).

    TIDAK menulis berkas apa pun. Tapi MEMANG menulis ke DB: `sinkron_pseudonim`
    membuat `pid` untuk pasien yang belum punya.
    """
    from app.core.csv_writer import dict_list_to_csv_bytes
    from app.services.clinical_export_service import ClinicalExportService

    svc = ClinicalExportService(db)
    info_pid = svc.sinkron_pseudonim()

    # Pagar: setiap pasien HARUS punya pid sebelum apa pun ditulis. Kalau ada yang
    # hilang, lebih baik berhenti daripada diam-diam membuat pid baru untuk pasien
    # yang sudah pernah keluar dengan pid lain.
    if info_pid["total_pid"] < info_pid["total_pasien"]:
        raise RuntimeError(
            f"Peta pseudonim tidak lengkap: {info_pid['total_pid']} pid untuk "
            f"{info_pid['total_pasien']} pasien. Ekspor dibatalkan — pid yang "
            f"hilang berarti riwayat longitudinal pasien itu akan terputus.")

    datasets, data_map, total = [], {}, 0
    for i, entry in enumerate(svc.REGISTRY, 1):
        rows = getattr(svc, entry["method"])(tgl_dari, tgl_sampai)
        data = dict_list_to_csv_bytes(rows)
        fname = f"{i:02d}_{entry['name']}.csv"
        datasets.append({"name": entry["name"], "file": fname,
                         "rows": len(rows),
                         "sha256": hashlib.sha256(data).hexdigest()})
        data_map[fname] = data
        total += len(rows)
    return datasets, data_map, total, _fingerprint(datasets), info_pid


# ---------------------------------------------------------------- export log
def _log_path(out_dir: str) -> str:
    return os.path.join(out_dir, LOG_NAME)


def read_log(out_dir: str):
    entries, p = [], _log_path(out_dir)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


def last_matching(out_dir: str, tgl_dari, tgl_sampai):
    cocok = None
    d = tgl_dari.isoformat() if tgl_dari else None
    s = tgl_sampai.isoformat() if tgl_sampai else None
    for e in read_log(out_dir):
        if e.get("period_from") == d and e.get("period_to") == s:
            cocok = e
    return cocok


# ---------------------------------------------------------------- write
def write_batch(out_dir, tgl_dari, tgl_sampai, datasets, data_map, total,
                content_fp, info_pid, *, triggered_by="owner", keep=30):
    periksa_drop(out_dir)
    recipient = _recipient()          # gagal DI SINI, sebelum apa pun ditulis
    os.makedirs(out_dir, exist_ok=True)

    now = datetime.now(WIB)
    stamp = now.strftime("%Y%m%dT%H%M")
    dari_s = tgl_dari.isoformat() if tgl_dari else "awal"
    sampai_s = tgl_sampai.isoformat() if tgl_sampai else "kini"
    batch_id = f"clinical-{dari_s}_{sampai_s}-{stamp}"
    zname = f"sehati_clinical_{dari_s}_{sampai_s}_{stamp}.zip"
    ztmp = os.path.join(out_dir, zname + ".tmp")
    zplain = os.path.join(out_dir, zname)
    zenc = zplain + ".age"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_system": "sehati-emr-pos",
        "pack": "clinical",
        "batch_id": batch_id,
        "period_from": tgl_dari.isoformat() if tgl_dari else None,
        "period_to": tgl_sampai.isoformat() if tgl_sampai else None,
        "exported_at": now.isoformat(),
        "triggered_by": triggered_by,
        "content_fingerprint": content_fp,
        "dataset_count": len(datasets),
        "total_rows": total,
        "datasets": datasets,
        "pseudonim": {"pid_baru_dibuat": info_pid["dibuat"],
                      "total_pid": info_pid["total_pid"]},
        # Ditulis di dalam paket supaya penerima tidak pernah bisa menyangka
        # ini data anonim. Kalimatnya sengaja untuk dibaca manusia.
        "PERINGATAN": (
            "PSEUDONIM, BUKAN ANONIM. Teks bebas (anamnesa, keluhan_utama) "
            "dikirim apa adanya dan bisa memuat nama, telepon, atau alamat di "
            "dalam kalimat. Diagnosa langka + tanggal sudah cukup untuk "
            "mengenali orang di klinik kecil. Perlakukan sebagai data rahasia: "
            "jangan taruh di cloud, git, atau folder tersinkron."
        ),
    }

    with zipfile.ZipFile(ztmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for d in datasets:
            z.writestr(d["file"], data_map[d["file"]])
        z.writestr("manifest.json", json.dumps(manifest, indent=2,
                                               ensure_ascii=False, default=str))
    os.replace(ztmp, zplain)          # atomik di volume yang sama

    # Enkripsi lalu HAPUS yang polos. Bukan "nanti dibersihkan" — kalau proses
    # berhenti di antaranya, yang tertinggal adalah SOAP pasien tanpa perlindungan.
    try:
        subprocess.run(["age", "-r", recipient, "-o", zenc, zplain],
                       check=True, capture_output=True)
    finally:
        if os.path.exists(zplain):
            os.remove(zplain)
    if not os.path.exists(zenc):
        raise EnkripsiTidakTersediaError(
            f"age tidak menghasilkan {zenc}. ZIP polos sudah dihapus; tidak ada "
            f"paket yang tertinggal tanpa perlindungan.")

    entry = {
        "batch_id": batch_id, "zip": os.path.basename(zenc),
        "period_from": manifest["period_from"], "period_to": manifest["period_to"],
        "exported_at": now.isoformat(), "content_fingerprint": content_fp,
        "total_rows": total, "triggered_by": triggered_by, "encrypted": True,
        "datasets": [{"name": d["name"], "rows": d["rows"], "sha256": d["sha256"]}
                     for d in datasets],
    }
    with open(_log_path(out_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    purge_old(out_dir, keep)
    return {"batch_id": batch_id, "zip": os.path.basename(zenc), "path": zenc,
            "total_rows": total, "content_fingerprint": content_fp,
            "exported_at": now.isoformat(), "encrypted": True}


def purge_old(out_dir: str, keep: int):
    paket = sorted((f for f in os.listdir(out_dir)
                    if f.startswith("sehati_clinical_") and f.endswith(".age")),
                   reverse=True)
    for f in paket[keep:]:
        try:
            os.remove(os.path.join(out_dir, f))
        except OSError:
            pass
    for f in os.listdir(out_dir):     # .tmp yatim & polos yang tertinggal
        if f.endswith(".tmp") or (f.startswith("sehati_clinical_")
                                  and f.endswith(".zip")):
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def smart_export(db, out_dir=None, tgl_dari=None, tgl_sampai=None, *,
                 force=False, triggered_by="owner", keep=30):
    """Ekspor klinis. Rentang None = SEJAK AWAL DATA (keputusan dr. Hansen).

    Return {status: 'no_change'|'exported', ...}
    """
    out_dir = out_dir or DEFAULT_DROP
    periksa_drop(out_dir)
    _recipient()                      # gagal sebelum menyentuh DB

    datasets, data_map, total, fp, info_pid = compute_datasets(
        db, tgl_dari, tgl_sampai)
    prev = last_matching(out_dir, tgl_dari, tgl_sampai) if os.path.isdir(out_dir) else None
    sama = bool(prev and prev.get("content_fingerprint") == fp)

    if sama and not force:
        return {"status": "no_change", "content_fingerprint": fp,
                "total_rows": total, "last": prev, "datasets": datasets,
                "pseudonim": info_pid}

    res = write_batch(out_dir, tgl_dari, tgl_sampai, datasets, data_map, total,
                      fp, info_pid, triggered_by=triggered_by, keep=keep)
    res["status"] = "exported"
    res["forced_identical"] = sama
    res["datasets"] = datasets
    res["pseudonim"] = info_pid
    return res
