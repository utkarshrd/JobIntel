"""Alembic environment: the database URL and metadata come from the application itself (DATABASE_URL / models)."""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import models  # noqa: E402,F401  (registers every table on Base.metadata)
from backend.app.core.config import settings  # noqa: E402
from backend.app.core.database import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
# `alembic -x url=postgresql+psycopg2://...` overrides the application URL (used to generate against a scratch DB)
DB_URL = context.get_x_argument(as_dictionary=True).get("url") or settings.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(url=DB_URL, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DB_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
