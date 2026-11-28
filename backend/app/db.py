"""Database connection (SQLite, one file)."""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(engine)
    add_missing_columns()


def add_missing_columns():
    """Add columns introduced after a database file was created, so an existing database
    keeps working after an update (no reset needed)."""
    existing = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not existing.has_table(table.name):
                continue
            present = {c["name"] for c in existing.get_columns(table.name)}
            for col in table.columns:
                if col.name in present:
                    continue
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                sql_default = "" if default is None else f" DEFAULT {int(default) if isinstance(default, bool) else repr(default)}"
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}{sql_default}'))
