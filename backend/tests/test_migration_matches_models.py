"""The Alembic revision and the ORM models must describe the same schema.

Runs the migration on a scratch database and asserts that Alembic detects no
difference against ``Base.metadata`` afterwards, so the two can never drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.conftest import TEST_DATABASE_URL, requires_database

pytestmark = [pytest.mark.database, requires_database]

IGNORED_TABLES = {"alembic_version"}


def _upgrade_to_head(connection: Connection) -> None:
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    config.attributes["connection"] = connection
    upgrade(config, "head")




def _diff_against_models(connection: Connection) -> list:
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "include_name": lambda name, type_, _: (
                not (type_ == "table" and name in IGNORED_TABLES)
            ),
        },
    )
    return compare_metadata(context, Base.metadata)


async def test_migration_produces_the_model_schema() -> None:
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade_to_head)
        async with engine.connect() as connection:
            differences = await connection.run_sync(_diff_against_models)
    finally:
        await engine.dispose()

    assert differences == [], f"migration drifted from the models: {differences}"
