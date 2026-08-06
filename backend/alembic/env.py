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
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Set by callers that already own a (sync) connection - tests and deploy scripts.
#: When present it decides the target database, so no URL is needed or read.
_EXISTING_CONNECTION = config.attributes.get("connection")


def _configured_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("ARGUS_DATABASE_URL must be set before running migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_configured_url(),
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
    config.set_main_option("sqlalchemy.url", _configured_url())
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif _EXISTING_CONNECTION is not None:
    _run(_EXISTING_CONNECTION)
else:
    asyncio.run(run_migrations_online())
