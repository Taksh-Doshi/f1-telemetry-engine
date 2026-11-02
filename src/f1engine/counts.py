"""Print the number of stored rows in each ingestion table."""

from sqlalchemy import text

from f1engine.db import get_engine, run_schema


TABLES = (
    "events",
    "sessions",
    "drivers",
    "laps",
    "stints",
    "weather",
    "lap_telemetry_summary",
    "telemetry_samples",
)


def main() -> None:
    """Query each known table and print its row count."""
    engine = get_engine()
    try:
        run_schema(engine)
        with engine.connect() as connection:
            print("Table counts:")
            for table in TABLES:
                # Table names come only from the fixed list above.
                count = connection.execute(
                    text(f"SELECT count(*) FROM {table}")
                ).scalar_one()
                print(f"{table}: {count}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
