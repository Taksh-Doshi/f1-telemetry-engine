"""Database connection and schema setup helpers."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / "sql" / "schema"


def get_engine() -> Engine:
    """Create a SQLAlchemy engine using DATABASE_URL from the project .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Add it to {PROJECT_ROOT / '.env'} "
            "or the process environment."
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def run_schema(engine: Engine | None = None) -> None:
    """Apply numbered SQL schema files in order inside one transaction."""
    owns_engine = engine is None
    active_engine = engine or get_engine()

    try:
        schema_files = sorted(SCHEMA_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        if not schema_files:
            raise FileNotFoundError(f"No numbered schema files found in {SCHEMA_DIR}")

        with active_engine.begin() as connection:
            for schema_file in schema_files:
                sql_text = schema_file.read_text(encoding="utf-8")
                for statement in sql_text.split(";"):
                    statement = statement.strip()
                    if statement:
                        connection.exec_driver_sql(statement)
    finally:
        if owns_engine:
            active_engine.dispose()