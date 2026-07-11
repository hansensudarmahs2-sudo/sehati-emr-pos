"""
Owner-only: monitor util cache antrian (hit/miss) — bukti cache bekerja.

Read-only + kontrol debug: reset counter, kosongkan cache, kill-switch on/off.
GET /web/_cache-stats           halaman (auto-refresh 2s)
POST /web/_cache-stats/reset    nolkan counter
POST /web/_cache-stats/clear    kosongkan isi cache
POST /web/_cache-stats/toggle   nyalakan/matikan cache (kill-switch runtime)
"""
from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.deps import DbSession
from app.core import ttl_cache
from app.web.routes._shared import get_user_from_cookie, require_owner_only

router = APIRouter(tags=["Web Cache Stats"])


def _guard(request: Request, db):
    user = get_user_from_cookie(request, db)
    if user is None:
        return None, RedirectResponse("/web/login", status_code=status.HTTP_303_SEE_OTHER)
    if not require_owner_only(user):
        return None, HTMLResponse("<div style='padding:2rem'>403 — Owner only.</div>", status_code=403)
    return user, None


def _page(request: Request) -> HTMLResponse:
    s = ttl_cache.stats()
    tok = getattr(getattr(request, "state", None), "csrf_token", "") or ""
    on = s["enabled"]
    badge = ("<span style='background:#0a7d33;color:#fff;padding:2px 10px;border-radius:12px'>AKTIF</span>"
             if on else
             "<span style='background:#b00020;color:#fff;padding:2px 10px;border-radius:12px'>MATI</span>")
    ratio_pct = round(s["hit_ratio"] * 100, 1)
    csrf = f"<input type=hidden name=csrf_token value='{tok}'>"

    def card(label, val, color="#1f3864"):
        return (f"<div style='background:#fff;border-radius:10px;padding:14px 18px;"
                f"box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:130px'>"
                f"<div style='font-size:12px;color:#6b7280'>{label}</div>"
                f"<div style='font-size:26px;font-weight:700;color:{color};margin-top:4px'>{val}</div></div>")

    body = f"""<!doctype html><html lang=id><head><meta charset=utf-8>
<meta http-equiv=refresh content=2>
<title>Cache Stats</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#1f2937;margin:0;padding:24px}}
h1{{font-size:18px;color:#1f3864;margin:0 0 4px}} p{{color:#6b7280;font-size:13px;margin:0 0 16px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
.btn{{border:0;padding:9px 16px;border-radius:6px;font-size:13px;cursor:pointer;color:#fff}}
form{{display:inline}} a{{color:#1f3864}}</style></head><body>
<h1>Monitor Cache Antrian</h1>
<p>Status: {badge} &nbsp;·&nbsp; auto-refresh 2 detik &nbsp;·&nbsp; TTL antrian: {ttl_cache.ANTRIAN_TTL:.0f}s &nbsp;·&nbsp; <a href='/web/dashboard'>← Dashboard</a></p>
<div class=cards>
  {card("Hits (dari cache)", s["hits"], "#0a7d33")}
  {card("Misses (query DB)", s["misses"], "#b00020")}
  {card("Hit ratio", f"{ratio_pct}%")}
  {card("Entri tersimpan", f"{s['size']} / {s['max_entries']}")}
  {card("Evictions (LRU)", s["evictions"])}
</div>
<form method=post action='/web/_cache-stats/reset'>{csrf}<button class=btn style='background:#1f3864'>Reset counter</button></form>
<form method=post action='/web/_cache-stats/clear'>{csrf}<button class=btn style='background:#6b7280'>Kosongkan cache</button></form>
<form method=post action='/web/_cache-stats/toggle'>{csrf}<button class=btn style='background:{"#b00020" if on else "#0a7d33"}'>{"Matikan cache" if on else "Nyalakan cache"}</button></form>
<p style='margin-top:18px;color:#9ca3af'>Hits naik cepat + misses stabil = cache bekerja. Matikan cache → semua poll jadi miss (bukti kontras).</p>
</body></html>"""
    return HTMLResponse(body)


@router.get("/_cache-stats", response_class=HTMLResponse)
def cache_stats(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    return _page(request)


@router.post("/_cache-stats/reset")
def cache_stats_reset(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    ttl_cache.reset_stats()
    return RedirectResponse("/web/_cache-stats", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/_cache-stats/clear")
def cache_stats_clear(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    ttl_cache.clear()
    return RedirectResponse("/web/_cache-stats", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/_cache-stats/toggle")
def cache_stats_toggle(request: Request, db: DbSession):
    user, resp = _guard(request, db)
    if resp:
        return resp
    ttl_cache.set_enabled(not ttl_cache.is_enabled())
    return RedirectResponse("/web/_cache-stats", status_code=status.HTTP_303_SEE_OTHER)


__all__ = ["router"]
