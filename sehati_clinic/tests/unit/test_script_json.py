"""
P1-4 (AUDIT_SEHATI_2026-07-10) — stored XSS via JSON di dalam <script>.

`json.dumps` biasa TIDAK meng-escape '<' '>' '&', jadi nilai master-data seperti
'</script><img src=x onerror=...>' bisa KELUAR dari blok <script> dan dieksekusi.
`script_json` harus meng-escape pemicu breakout tapi tetap JSON valid.
"""
import json

from app.web.routes._shared import script_json


def test_escape_breakout_script():
    payload = [{"nama": "</script><img src=x onerror=alert(1)>"}]
    out = script_json(payload)
    assert "</script>" not in out, "harus tak ada '</script>' mentah (breakout)."
    assert "\\u003c/script\\u003e" in out
    assert "\\u003cimg" in out


def test_tetap_json_valid_dan_bisa_di_parse():
    out = script_json({"a": 1, "b": "obat 500mg", "c": [1, 2]})
    assert json.loads(out) == {"a": 1, "b": "obat 500mg", "c": [1, 2]}


def test_ampersand_dan_gt_di_escape():
    out = script_json({"x": "a & b > c"})
    assert "&" not in out and ">" not in out
    assert json.loads(out) == {"x": "a & b > c"}


def test_pola_script_block_tak_bisa_breakout():
    """Bukti pola nyata: script_json + `| safe` di dalam <script> tak bisa dijebol."""
    from app.web.routes._shared import templates

    blob = script_json([{"label": "</script><script>alert(1)</script>"}])
    html = templates.env.from_string(
        '<script id="x" type="application/json">{{ blob | safe }}</script>'
    ).render(blob=blob)
    # Hanya SATU '</script>' (penutup sah) — data ter-escape, tak ada tag script kedua.
    assert html.count("</script>") == 1
    assert "<script>alert" not in html
