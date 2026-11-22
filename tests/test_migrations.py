"""Alembic migration upgrade and downgrade tests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_TABLES = {"users", "datasets", "conversations", "messages", "ai_usage"}


def test_alembic_upgrade_and_downgrade_manage_core_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert CORE_TABLES.issubset(set(inspector.get_table_names()))

            dataset_foreign_keys = inspector.get_foreign_keys("datasets")
            assert any(
                foreign_key["referred_table"] == "users"
                and foreign_key["options"].get("ondelete") == "CASCADE"
                for foreign_key in dataset_foreign_keys
            )
            dataset_columns = {column["name"] for column in inspector.get_columns("datasets")}
            message_columns = {column["name"] for column in inspector.get_columns("messages")}
            assert "error_message" in dataset_columns
            assert "analysis_plan" in message_columns

        command.downgrade(config, "base")

        with engine.connect() as connection:
            remaining_tables = set(inspect(connection).get_table_names())
            assert CORE_TABLES.isdisjoint(remaining_tables)
    finally:
        engine.dispose()
