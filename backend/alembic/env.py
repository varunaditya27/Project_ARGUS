"""Alembic environment.

The URL always comes from ``ARGUS_DATABASE_URL`` so migrations, the API and the
benchmarks can never drift onto different databases.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context
from app.core.config import get_settings
from app.db import models  # noqa: F401 - imported for metadata registration
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
if not settings.database_url:
    raise RuntimeError("ARGUS_DATABASE_URL must be set before running migrations")
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


#: Set by callers that already own a (sync) connection - tests and deploy scripts.
_EXISTING_CONNECTION = config.attributes.get("connection")

if context.is_offline_mode():
    run_migrations_offline()
elif _EXISTING_CONNECTION is not None:
    _run(_EXISTING_CONNECTION)
else:
    asyncio.run(run_migrations_online())
