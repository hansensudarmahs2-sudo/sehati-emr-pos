"""
CSRF protection — double-submit cookie pattern.

Implementasi pure ASGI middleware (BUKAN BaseHTTPMiddleware) untuk menghindari
bug body-consumption: BaseHTTPMiddleware konsumsi receive stream saat
request.body() di middleware, downstream FastAPI Form() dapat 422.

Pure ASGI memungkinkan kita read body sekali, validate, lalu replay body
ke downstream app via custom receive callable.

Cara kerja:
- GET /web/*: middleware set cookie csrf_token (random) + attach ke request.state.
- POST /web/*: middleware baca body, parse urlencoded form, validate
  csrf_token == cookie, lalu replay body ke downstream.
- /api/v1/*: skip total (JWT bearer immune to CSRF).
- multipart/form-data tidak di-support (kita tidak punya file upload form).

Token: secrets.token_urlsafe(32) — 256-bit random URL-safe.
Validasi: secrets.compare_digest (constant-time, anti timing attack).
"""

import logging
import re
import secrets
import urllib.parse

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings


_logger = logging.getLogger("app.csrf")


CSRF_COOKIE_NAME = "sehati_csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_TOKEN_BYTES = 32
COOKIE_MAX_AGE = 21600  # 6 jam


def generate_csrf_token() -> str:
    """256-bit random token URL-safe."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def _get_cookie_from_headers(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    """Parse cookie value dari ASGI headers list."""
    for key, value in headers:
        if key == b"cookie":
            cookies = value.decode("latin-1")
            for item in cookies.split(";"):
                k, _, v = item.strip().partition("=")
                if k == name:
                    return v
    return None


def _build_error_response(msg: str) -> tuple[bytes, dict]:
    """Build 403 HTML response (Bahasa Indonesia)."""
    body = (
        "<div style='padding:2rem;font-family:sans-serif;max-width:600px;"
        "margin:2rem auto;background:#fef2f2;border:1px solid #fecaca;"
        "border-radius:0.5rem;'>"
        "<h2 style='color:#b91c1c;margin:0 0 0.5rem 0;'>"
        "&#9888; Token Keamanan Tidak Valid</h2>"
        f"<p style='color:#7f1d1d;margin:0 0 1rem 0;'>{msg}</p>"
        "<a href='/web/dashboard' style='color:#1d4ed8;'>"
        "&larr; Kembali ke Dashboard</a>"
        "</div>"
    ).encode("utf-8")
    return body, {"content-type": "text/html; charset=utf-8"}


async def _send_error(send: Send, msg: str) -> None:
    """Kirim 403 response via ASGI send."""
    body, extra_headers = _build_error_response(msg)
    headers = [
        (b"content-type", b"text/html; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
    ]
    await send({"type": "http.response.start", "status": 403, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _read_full_body(receive: Receive) -> bytes:
    """Baca seluruh request body dari ASGI receive."""
    chunks: list[bytes] = []
    more = True
    while more:
        msg = await receive()
        if msg["type"] != "http.request":
            break
        chunks.append(msg.get("body", b""))
        more = msg.get("more_body", False)
    return b"".join(chunks)


class CSRFMiddleware:
    """Pure ASGI middleware untuk CSRF protection."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Skip non-HTTP (websocket, lifespan)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Skip non-web routes (API pakai JWT bearer)
        if not path.startswith("/web"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        headers: list = scope.get("headers", [])
        cookie_token = _get_cookie_from_headers(headers, CSRF_COOKIE_NAME)

        # ===== POST validation =====
        if method == "POST":
            if not cookie_token:
                await _send_error(
                    send,
                    "Sesi CSRF tidak ditemukan. Refresh halaman lalu coba lagi.",
                )
                return

            # Read body once
            body = await _read_full_body(receive)

            # Detect Content-Type — multipart vs urlencoded
            content_type = b""
            for k, v in headers:
                if k.lower() == b"content-type":
                    content_type = v.lower()
                    break
            is_multipart = b"multipart/form-data" in content_type

            form_token = ""
            try:
                if is_multipart:
                    # Multipart form (file upload) — extract csrf_token via regex.
                    # Format: ...Content-Disposition: form-data; name="csrf_token"\r\n\r\n<value>\r\n--boundary
                    pattern = (
                        rb'name="'
                        + CSRF_FORM_FIELD.encode("utf-8")
                        + rb'"\r?\n\r?\n([^\r\n]+)'
                    )
                    m = re.search(pattern, body)
                    if m:
                        form_token = m.group(1).decode("utf-8", errors="replace").strip()
                else:
                    # urlencoded form
                    body_str = body.decode("utf-8", errors="replace")
                    parsed = urllib.parse.parse_qs(body_str, keep_blank_values=True)
                    tok_list = parsed.get(CSRF_FORM_FIELD, [])
                    if tok_list:
                        form_token = tok_list[0]
            except Exception as exc:  # noqa: BLE001 — graceful degradation by design
                # Body parsing fail → biarkan form_token="" sehingga validation
                # di bawah akan reject dengan pesan CSRF invalid.
                _logger.warning(
                    "CSRF body parse failed (path=%s, multipart=%s): %s",
                    scope.get("path", "?"), is_multipart, exc,
                )

            if not form_token or not secrets.compare_digest(
                form_token, cookie_token
            ):
                await _send_error(
                    send,
                    "Token CSRF tidak valid. Refresh halaman lalu coba lagi.",
                )
                return

            # Attach token ke scope.state untuk Jinja template re-render
            scope.setdefault("state", {})
            if isinstance(scope["state"], dict):
                scope["state"]["csrf_token"] = cookie_token

            # Replay body ke downstream
            body_sent = False

            async def replay_receive() -> dict:
                nonlocal body_sent
                if body_sent:
                    # Edge case: shouldn't be called again after more_body=False,
                    # tapi defensive — return empty completed message
                    # (BUKAN http.disconnect, karena itu trigger ClientDisconnect
                    # exception di Starlette stream()).
                    return {"type": "http.request", "body": b"", "more_body": False}
                body_sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }

            await self.app(scope, replay_receive, send)
            return

        # ===== GET/HEAD — ensure cookie set =====
        token = cookie_token or generate_csrf_token()

        # Attach token to scope.state — request.state.csrf_token akan baca dari sini
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["csrf_token"] = token

        # Wrap send untuk inject Set-Cookie header kalau cookie belum ada
        if cookie_token:
            # Cookie sudah ada, langsung pass through
            await self.app(scope, receive, send)
            return

        # Need to inject Set-Cookie header pada response start
        cookie_value = (
            f"{CSRF_COOKIE_NAME}={token}; Max-Age={COOKIE_MAX_AGE}; "
            f"Path=/; SameSite=Lax"
        )
        if settings.cookie_secure:
            cookie_value += "; Secure"

        async def send_with_csrf(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append((b"set-cookie", cookie_value.encode("latin-1")))
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, send_with_csrf)


__all__ = [
    "CSRFMiddleware",
    "CSRF_COOKIE_NAME",
    "CSRF_FORM_FIELD",
    "generate_csrf_token",
]
