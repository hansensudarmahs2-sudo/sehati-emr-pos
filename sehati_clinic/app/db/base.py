"""
SQLAlchemy declarative base.

Semua ORM models inherit dari `Base` di sini.
Untuk Alembic auto-generate migration, semua models harus di-import via
`app.db.models.__init__.py` supaya `Base.metadata` punya info tentang
semua tabel.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class untuk semua SQLAlchemy ORM models."""

    pass
