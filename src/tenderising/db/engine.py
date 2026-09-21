"""SQLAlchemy engine and session factory.

SQLite (WAL) to start (§10); PostgreSQL is the documented later path on
concurrent writers / FTS / multi-user.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from tenderising.config import DATA_DIR, DB_PATH


def make_engine(url: str | None = None):
    if url is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{DB_PATH}"
    engine = create_engine(url, future=True)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # Let a writer wait briefly for another writer's short transaction to
            # release, instead of failing fast with "database is locked".
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)
