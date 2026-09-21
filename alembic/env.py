from logging.config import fileConfig

from sqlalchemy import engine_from_config, event, pool

from alembic import context
from tenderising.config import DB_PATH
from tenderising.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata for autogenerate.
target_metadata = Base.metadata


def _sqlalchemy_url() -> str:
    # Prefer an explicit URL in alembic.ini; default to the curated SQLite DB.
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DB_PATH}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_sqlalchemy_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sqlalchemy_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Match the app engine's busy_timeout so migrations wait out short-lived
    # writer locks instead of failing immediately with "database is locked".
    if _sqlalchemy_url().startswith("sqlite"):

        @event.listens_for(connectable, "connect")
        def _set_busy_timeout(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
