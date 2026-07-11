"""Logika PURE konektor antropometri sisi Sehati (tanpa settings/DB/network).

Membangun payload `sehati_antro_input` (CONTRACT_SEHATI_ANTROPOMETRI_v1) dari
primitif domain. Dipisah agar mudah di-unit-test tanpa boot config/DB.
"""
from __future__ import annotations

SCHEMA_VERSION = "1.0"

# jenis_kelamin Sehati (L/P) -> kontrak (male/female)
SEX_MAP = {"L": "male", "P": "female"}

# role Sehati -> kontrak (doctor|nurse|fo). Non-dokter tak bisa APPROVE di modul.
ROLE_MAP = {
    "Dokter": "doctor", "Owner": "doctor", "Admin": "doctor", "Superadmin": "doctor",
    "Perawat": "nurse", "FO": "fo",
}


def map_sex(jk: str | None) -> str:
    return SEX_MAP.get((jk or "").upper(), "male")


def map_role(role: str | None) -> str:
    return ROLE_MAP.get((role or "").strip(), "nurse")


# Urutan titik skinfold per jenis kelamin (Sehati titik_1/2/3 -> key kontrak).
# Pria: dada, abdomen, paha · Wanita: trisep, suprailiac, paha.
SKINFOLD_ORDER = {"L": ("chest", "abdomen", "thigh"), "P": ("triceps", "suprailiac", "thigh")}


def skinfold_named(jenis_kelamin: str, titik_1=None, titik_2=None, titik_3=None) -> dict:
    """Petakan titik_1/2/3 Sehati -> key bernama sesuai jenis kelamin (untuk JSON)."""
    keys = SKINFOLD_ORDER.get((jenis_kelamin or "").upper(), SKINFOLD_ORDER["L"])
    return {k: v for k, v in zip(keys, (titik_1, titik_2, titik_3)) if v is not None}


def protocol_for(sex: str) -> str:
    return "JP3_MALE" if sex == "male" else "JP3_FEMALE"


def build_intake_payload(
    *,
    rm_number: str,
    encounter_id,
    assessed_at: str,
    actor_role: str,
    actor_staf_id,
    actor_name: str | None = None,
    jenis_kelamin: str,          # 'L'/'P' (Sehati)
    age: int,
    dob: str | None = None,
    height_cm: float | None = None,   # OPSIONAL: Sehati boleh kirim atau tidak
    weight_kg: float | None = None,   # (modul yang mengisi bila kosong)
    waist_cm: float | None = None,
    skinfold_mm: dict | None = None,   # key bernama: chest/abdomen/thigh atau triceps/suprailiac/thigh
    screening: dict | None = None,
    chronic_codes: list | None = None,
    patient_goal: str | None = None,
    return_url: str | None = None,
    idempotency_key: str | None = None,
    activity_level: str | None = None,
    patient_constraints: str | None = None,
    timeline_note: str | None = None,
    on_weight_med: bool = False,
) -> dict:
    sex = map_sex(jenis_kelamin)
    return {
        "schema_version": SCHEMA_VERSION,
        "request_meta": {
            "source_system": "sehati",
            "rm_number": rm_number,
            "encounter_id": str(encounter_id),
            "assessed_at": assessed_at,
            "idempotency_key": idempotency_key or f"sehati-antro-{encounter_id}",
            "return_url": return_url,
        },
        "actor": {"role": map_role(actor_role), "staf_id": str(actor_staf_id), "name": actor_name},
        "patient": {"sex": sex, "age": age, "dob": dob, "local_patient_id": rm_number},
        "measurements": {
            "height_cm": height_cm, "weight_kg": weight_kg, "waist_cm": waist_cm,
            "skinfold_protocol": protocol_for(sex), "skinfold_mm": skinfold_mm or {},
        },
        "screening": screening or {},
        "chronic": {"has_chronic_disease": bool(chronic_codes), "codes": chronic_codes or []},
        "activity_level": activity_level,
        "context": {
            "patient_constraints": patient_constraints,
            "timeline_note": timeline_note,
            "on_weight_med": on_weight_med,
        },
        "patient_goal": patient_goal,
    }
