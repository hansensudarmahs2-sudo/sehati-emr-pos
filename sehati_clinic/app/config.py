"""
Application configuration — baca dari environment variables (.env).

Pakai Pydantic Settings untuk type-safe config loading.
Akses config: `from app.config import settings`.
"""

from functools import lru_cache
from pydantic import Field, model_validator
from pathlib import Path as _Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Aplikasi settings — di-load otomatis dari .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Application -----
    app_name: str = Field(default="Klinik Sehati API")
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    # ----- Database -----
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=3306)
    db_user: str = Field(default="klinik_dev")
    db_password: str = Field(default="")
    db_name: str = Field(default="db_sehati")

    @property
    def database_url(self) -> str:
        """SQLAlchemy connection URL untuk MySQL via PyMySQL."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    # ----- JWT -----
    jwt_secret_key: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_hours: int = Field(default=6)

    # ----- Web Cookie Security -----
    # Default True (failure-secure untuk production HTTPS).
    # Localhost dev WAJIB override ke false di .env, karena browser tidak
    # kirim cookie Secure lewat HTTP — login akan loop kalau dev pakai True.
    cookie_secure: bool = Field(default=True)
    # P1-3: daftar proxy tepercaya (IP/CIDR, koma) untuk mem-percaya X-Forwarded-For.
    # Default = loopback (nginx satu host). Kosongkan = TIDAK pernah percaya XFF (pakai peer).
    trusted_proxies: str = Field(default="127.0.0.1,::1")

    # ----- CORS -----
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:8000"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins jadi list."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # ----- Logging -----
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="text")

    # ----- Timezone -----
    timezone: str = Field(default="Asia/Jakarta")

    # ----- RM Numbering (DEC-071a) -----
    # Prefix huruf cabang sebelum nomor RM (mis. "A" -> "A-260626-001").
    # Tiap server cabang set hurufnya sendiri di .env (cabang ke-2 = "B", dst).
    # Future-proofing supaya RM tidak bentrok saat multi-cabang.
    rm_clinic_prefix: str = Field(default="A")

    # ----- Konektor AI Antropometri (AN-L1) -----
    # Kosong = konektor NONAKTIF (aman default). Isi saat modul antropometri siap.
    # antro_base_url: alamat LAN modul (mis. http://pc-a.local:8051), TANPA trailing slash wajib.
    # antro_intake_token: Token A (Sehati -> modul /intake). Nilai SAMA di .env modul.
    # sehati_writeback_token: Token B (modul -> Sehati /connector/antro/*). Sehati yang terbitkan.
    antro_base_url: str = Field(default="")
    antro_intake_token: str = Field(default="")
    sehati_writeback_token: str = Field(default="")

    # ----- Idle-timeout sesi (keamanan, V3.3.2) -----
    # Auto-logout klien setelah tak ada interaksi nyata. 0/negatif = nonaktif.
    session_idle_minutes: int = Field(default=60)
    session_idle_warn_minutes: int = Field(default=2)

    # ----- Security headers: CSP + HSTS (backlog S1, ASVS V14.4.1) -----
    # CSP: default AKTIF dengan 'unsafe-inline' (app pakai banyak inline script/style;
    # DEC-073 self-host tanpa CDN). Menutup origin luar (anti-exfil/CDN nyasar),
    # clickjacking (frame-ancestors), dan form-hijack (form-action). report_only=true
    # → kirim header Content-Security-Policy-Report-Only (tidak menegakkan; untuk uji).
    security_csp_enabled: bool = Field(default=True)
    security_csp_report_only: bool = Field(default=False)
    security_csp_policy: str = Field(
        default=(
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'"
        )
    )
    # HSTS: default NONAKTIF (aktifkan di .env prod saat HTTPS konsisten, mis. via Cloudflare).
    # SENGAJA TANPA includeSubDomains → jangan paksa HTTPS ke photodex.joderma.id (LAN HTTP).
    security_hsts_enabled: bool = Field(default=False)
    security_hsts_max_age: int = Field(default=31536000)

    # ----- Helpers -----
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    # ----- A6 (DEC audit P2-1): guard boot produksi -----
    @model_validator(mode="after")
    def _guard_production_secret(self) -> "Settings":
        """Tolak boot di PRODUCTION kalau JWT secret masih default / terlalu pendek.

        Kalau ter-deploy dengan secret default, siapa pun yang tahu default itu bisa
        MEMALSUKAN token login (masuk sebagai user mana pun). Di development guard ini
        tidak aktif supaya tidak mengganggu dev/test.
        """
        if self.is_production:
            weak = (
                self.jwt_secret_key == "CHANGE_ME_IN_PRODUCTION"
                or len(self.jwt_secret_key) < 32
            )
            if weak:
                raise ValueError(
                    "BOOT PRODUCTION DITOLAK: jwt_secret_key masih default atau < 32 karakter. "
                    "Set JWT_SECRET_KEY di .env dengan string acak >= 32 karakter "
                    "(mis. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)."
                )
            # Audit ASVS V14.1/14.3.2 (hardening): debug ON di produksi = bocor traceback/path/versi.
            if self.app_debug:
                raise ValueError(
                    "BOOT PRODUCTION DITOLAK: APP_DEBUG=true di produksi membocorkan detail error. "
                    "Set APP_DEBUG=false di .env produksi."
                )
        return self




@lru_cache
def get_settings() -> Settings:
    """
    Cache instance Settings supaya tidak parse .env berulang kali.
    Pakai `@lru_cache` — instance pertama akan disimpan dan dipakai ulang.
    """
    return Settings()


# Convenience: `from app.config import settings`
settings = get_settings()
