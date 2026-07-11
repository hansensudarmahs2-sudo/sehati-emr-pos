"""Core file-drop export (DEC-066-R2) — DIPAKAI BERSAMA oleh CLI cron & tombol UI.

Menghasilkan SATU ZIP (15 CSV + manifest.json) yang ditulis ATOMIK (.tmp -> rename)
ke folder file-drop, plus fitur SMART: bandingkan "content fingerprint" periode yang
diminta dengan export terakhir untuk periode+entity yang sama (dari export_log.jsonl).
Bila identik -> beri sinyal 'no_change' agar pemanggil bisa minta konfirmasi.

Prinsip:
- Fingerprint = sha256 gabungan dari sha256 per-dataset (urut nama). Deterministik dan
  MENGABAIKAN exported_at/stamp yang selalu berubah.
- export_log.jsonl = jejak append-only di folder drop; ditulis baik oleh cron maupun UI,
  sehingga export manual bisa "melihat" apa yang sudah dihasilkan otomatis.
"""
import hashlib
import json
import os
import zipfile
from datetime import date, datetime, timezone, timedelta

SCHEMA_VERSION = "2.0"
WIB = timezone(timedelta(hours=7))
LOG_NAME = "export_log.jsonl"
DEFAULT_DROP = os.getenv("SEHATI_FINANCE_DROP", "/mnt/e/SehatiExport/finance_pack")

# Dataset non-finansial yang volatil (audit login/logout, catatan SOAP): tetap ikut
# di ZIP, tapi TIDAK dihitung ke fingerprint "sama persis" / diff — agar sekadar login
# atau edit klinis tidak dianggap "ada penambahan" untuk keperluan export Finance.
FINGERPRINT_EXCLUDE = {"staff_activity_raw", "medical_soap_raw"}


# ---------------------------------------------------------------- fingerprint
def _fingerprint(datasets) -> str:
    joined = "\n".join(
        f"{d['name']}:{d['sha256']}"
        for d in sorted(datasets, key=lambda x: x["name"])
        if d["name"] not in FINGERPRINT_EXCLUDE
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_datasets(db, tgl_dari: date, tgl_sampai: date):
    """Hitung 15 dataset di memori. Return (datasets_meta, data_map, total, content_fp).
    TIDAK menulis file apa pun."""
    from app.services.export_service import ExportService
    from app.core.csv_writer import dict_list_to_csv_bytes
    svc = ExportService(db)
    datasets, data_map, total = [], {}, 0
    for i, entry in enumerate(svc.DATASET_REGISTRY, 1):
        rows = getattr(svc, entry["method"])(tgl_dari, tgl_sampai, False)
        data = dict_list_to_csv_bytes(rows, columns=entry.get("default_columns"))
        fname = f"{i:02d}_{entry['name']}.csv"
        datasets.append({
            "name": entry["name"], "file": fname,
            "rows": len(rows), "sha256": hashlib.sha256(data).hexdigest(),
        })
        data_map[fname] = data
        total += len(rows)
    return datasets, data_map, total, _fingerprint(datasets)


# ---------------------------------------------------------------- export log
def _log_path(out_dir: str) -> str:
    return os.path.join(out_dir, LOG_NAME)


def read_log(out_dir: str):
    entries = []
    p = _log_path(out_dir)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def last_matching(out_dir: str, entity: str, tgl_dari: date, tgl_sampai: date):
    """Entry log TERAKHIR untuk entity + periode yang sama (atau None)."""
    match = None
    for e in read_log(out_dir):
        if (e.get("entity") == entity
                and e.get("period_from") == tgl_dari.isoformat()
                and e.get("period_to") == tgl_sampai.isoformat()):
            match = e
    return match


def _append_log(out_dir: str, entry: dict):
    with open(_log_path(out_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def diff_summary(prev_datasets, cur_datasets):
    """Bandingkan per-dataset. Return list {name, status(baru|berubah), delta_rows}."""
    prev = {d["name"]: d for d in (prev_datasets or [])}
    changed = []
    for d in cur_datasets:
        if d["name"] in FINGERPRINT_EXCLUDE:
            continue
        p = prev.get(d["name"])
        if p is None:
            if d["rows"]:
                changed.append({"name": d["name"], "status": "baru", "delta_rows": d["rows"]})
        elif p.get("sha256") != d["sha256"]:
            changed.append({"name": d["name"], "status": "berubah",
                            "delta_rows": d["rows"] - int(p.get("rows", 0))})
    return changed


# ---------------------------------------------------------------- write batch
def write_batch(out_dir, entity, tgl_dari, tgl_sampai, datasets, data_map, total,
                content_fp, *, triggered_by="cron", mode="auto", keep=30):
    os.makedirs(out_dir, exist_ok=True)
    now = datetime.now(WIB)
    stamp = now.strftime("%Y%m%dT%H%M")
    batch_id = f"{entity}-{tgl_dari}_{tgl_sampai}-{stamp}"
    zname = f"sehati_{entity}_{tgl_dari}_{tgl_sampai}_{stamp}.zip"
    ztmp = os.path.join(out_dir, zname + ".tmp")
    zfinal = os.path.join(out_dir, zname)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_system": "sehati-emr-pos",
        "entity": entity,
        "batch_id": batch_id,
        "period_from": tgl_dari.isoformat(),
        "period_to": tgl_sampai.isoformat(),
        "exported_at": now.isoformat(),
        "triggered_by": triggered_by,
        "mode": mode,
        "content_fingerprint": content_fp,
        "dataset_count": len(datasets),
        "total_rows": total,
        "datasets": datasets,
    }
    with zipfile.ZipFile(ztmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for d in datasets:
            z.writestr(d["file"], data_map[d["file"]])
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    os.replace(ztmp, zfinal)  # ATOMIK di volume yang sama

    _append_log(out_dir, {
        "batch_id": batch_id, "zip": zname, "entity": entity,
        "period_from": tgl_dari.isoformat(), "period_to": tgl_sampai.isoformat(),
        "exported_at": now.isoformat(), "content_fingerprint": content_fp,
        "total_rows": total, "triggered_by": triggered_by, "mode": mode,
        "datasets": [{"name": d["name"], "rows": d["rows"], "sha256": d["sha256"]}
                     for d in datasets],
    })
    purge_old(out_dir, keep)
    return {"batch_id": batch_id, "zip": zname, "path": zfinal,
            "total_rows": total, "content_fingerprint": content_fp, "exported_at": now.isoformat()}


def purge_old(out_dir: str, keep: int):
    zips = sorted((f for f in os.listdir(out_dir) if f.endswith(".zip")), reverse=True)
    for f in zips[keep:]:
        try:
            os.remove(os.path.join(out_dir, f))
        except OSError:
            pass
    for f in os.listdir(out_dir):  # .tmp yatim
        if f.endswith(".tmp"):
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


# ---------------------------------------------------------------- smart export
def smart_export(db, out_dir, entity, tgl_dari, tgl_sampai, *,
                 force=False, triggered_by="owner", mode="manual", keep=30):
    """Alur pintar untuk export MANUAL (UI/CLI).

    Return salah satu:
      {status: 'no_change', ...}  -> data identik dengan batch terakhir; pemanggil
                                      sebaiknya minta konfirmasi lalu ulang force=True.
      {status: 'exported', ...}   -> ZIP baru ditulis (data berubah / periode baru / force).
    """
    datasets, data_map, total, fp = compute_datasets(db, tgl_dari, tgl_sampai)
    prev = last_matching(out_dir, entity, tgl_dari, tgl_sampai)
    identical = bool(prev and prev.get("content_fingerprint") == fp)

    if identical and not force:
        return {
            "status": "no_change", "content_fingerprint": fp, "total_rows": total,
            "last": prev, "datasets": datasets,
            "period_from": tgl_dari.isoformat(), "period_to": tgl_sampai.isoformat(),
            "entity": entity,
        }

    res = write_batch(out_dir, entity, tgl_dari, tgl_sampai, datasets, data_map, total, fp,
                      triggered_by=triggered_by, mode=mode, keep=keep)
    res["status"] = "exported"
    res["forced_identical"] = identical  # True bila user memaksa walau data sama
    res["changed"] = diff_summary(prev.get("datasets") if prev else None, datasets)
    res["prev"] = prev
    res["period_from"] = tgl_dari.isoformat()
    res["period_to"] = tgl_sampai.isoformat()
    res["entity"] = entity
    return res
