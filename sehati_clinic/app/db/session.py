"""
Database engine & session factory.

Pakai pattern: 1 request = 1 session = 1 transaction.
SessionLocal() dipakai via dependency injection di FastAPI routers.

Untuk MVP kita pakai sync engine (bukan async) — lebih sederhana untuk
pemula dan tidak ada bottleneck I/O signifikan di skala klinik kecil.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

# ----- Engine -----
# echo=True akan log semua SQL query — bagus untuk debug, matikan di production
engine = create_engine(
    settings.database_url,
    echo=settings.app_debug and settings.is_development,
    pool_pre_ping=True,   # validate connection sebelum dipakai (handle disconnect)
    pool_recycle=280,     # recycle connection setiap ~5 menit (under MySQL wait_timeout default)
    pool_size=10,
    max_overflow=20,
    connect_args={"connect_timeout": 10},  # fast-fail kalau MySQL unreachable
)


# ----- Session factory -----
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,   # objek tetap accessible setelah commit
)


# ----- FastAPI dependency -----
def get_db() -> Session:
    """
    Dependency untuk FastAPI endpoints.

    Pakai:
        @router.get("/...")
        def my_endpoint(db: Session = Depends(get_db)):
            ...

    Session otomatis di-close setelah request selesai,
    rollback otomatis kalau ada exception unhandled.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
