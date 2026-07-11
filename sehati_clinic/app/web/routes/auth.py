"""
Auth web routes:
- GET  /web/login           — render form
- POST /web/login           — validate creds + set JWT cookie + redirect
- GET  /web/dashboard       — placeholder dashboard
- GET  /web/logout          — clear cookie + AuthService.logout
"""

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from datetime import date

from app.core.deps import DbSession
from app.services.auth_service import AuthService
from app.core.rate_limit import (
    get_client_ip,
    check_login_allowed,
    record_login_failure,
    clear_login_attempts,
)
from app.services.dashboard_service import DashboardService
from app.web.menu import get_menu_for_role
from app.web.routes._shared import (
    APP_NAME,
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    COOKIE_SECURE,
    get_klinik_nama_safe,
    get_user_from_cookie,
    role_value_of,
    templates,
)


router = APIRouter(tags=["Web Auth"])


# =============================================================================
# GET /web/login
# =============================================================================
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: DbSession):
    """Render login form. Kalau sudah login, redirect ke dashboard."""
    user = get_user_from_cookie(request, db)
    if user is not None:
        return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "username": "",
            "klinik_nama": get_klinik_nama_safe(db),
            "app_name": APP_NAME,
        },
    )


# =============================================================================
# POST /web/login
# =============================================================================
@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: DbSession,
    username: str = Form(...),
    password: str = Form(...),
):
    """Validate creds via AuthService, set JWT cookie, redirect ke dashboard.

    C2: rate limit per-IP (gagal saja) untuk cegah brute-force tanpa lockout akun.
    """
    ip = get_client_ip(request)
    allowed, retry_after = check_login_allowed(ip)
    if not allowed:
        mins = (retry_after + 59) // 60
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": (
                    f"Terlalu banyak percobaan login gagal dari perangkat ini. "
                    f"Coba lagi dalam ~{mins} menit."
                ),
                "username": username,
                "klinik_nama": get_klinik_nama_safe(db),
                "app_name": APP_NAME,
            },
            status_code=429,
        )

    service = AuthService(db)
    try:
        token_response = service.login(
            username=username, password=password, request=request,
        )
    except HTTPException as e:
        record_login_failure(ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": e.detail,
                "username": username,
                "klinik_nama": get_klinik_nama_safe(db),
                "app_name": APP_NAME,
            },
            status_code=200,
        )

    clear_login_attempts(ip)

    response = RedirectResponse(
        url="/web/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token_response.access_token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return response


# =============================================================================
# GET /web/dashboard
# =============================================================================
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: DbSession):
    """Render dashboard dengan stats real per role."""
    user = get_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)

    role_value = role_value_of(user)
    expired_at = (
        user.token_expired_at.strftime("%Y-%m-%d %H:%M:%S")
        if user.token_expired_at
        else "(unknown)"
    )

    today = date.today()
    try:
        stats = DashboardService(db).get_stats_for_role(actor=user, today=today)
    except Exception as e:
        stats = {"role": role_value, "kpi": [], "shortcuts": [], "_error": str(e)}

    today_label = today.strftime("%A, %d %B %Y")

    # Branding topbar: samakan dgn build_shell_context (mini-logo / logo klinik)
    _klinik_logo = _klinik_mini_logo = None
    try:
        from app.services.klinik_config_service import KlinikConfigService
        _cfg = KlinikConfigService(db).get_config()
        _klinik_logo = getattr(_cfg, "logo_path", None)
        _klinik_mini_logo = getattr(_cfg, "mini_logo_path", None)
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": {
                "id_staf": user.id_staf,
                "username": user.username,
                "nama_staf": user.nama_staf,
                "role": role_value,
            },
            "token_expired_at": expired_at,
            "menu_groups": get_menu_for_role(role_value),
            "current_path": request.url.path,
            "stats": stats,
            "today_label": today_label,
            "page_title": "Dashboard",
            "page_subtitle": "Ringkasan hari ini",
            "klinik_nama": get_klinik_nama_safe(db),
            "klinik_logo_path": _klinik_logo,
            "klinik_mini_logo_path": _klinik_mini_logo,
            "app_name": APP_NAME,
        },
    )


# =============================================================================
# POST /web/logout (A11: state-changing → POST + CSRF)
# =============================================================================
@router.post("/logout")
def logout(request: Request, db: DbSession):
    """Clear cookie, call AuthService.logout, redirect."""
    import logging
    _logger = logging.getLogger("app.auth")

    user = get_user_from_cookie(request, db)
    if user is not None:
        try:
            AuthService(db).logout(staf=user, request=request)
        except Exception as exc:  # noqa: BLE001 — graceful by design
            # Logout audit log gagal jangan block user dari clear cookie.
            # Cookie tetap di-clear di bawah. Log warning supaya visible.
            _logger.warning("AuthService.logout failed (id_staf=%s): %s", user.id_staf, exc)

    response = RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


__all__ = ["router"]
