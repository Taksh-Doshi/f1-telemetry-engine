"""Copy the locally supported F1 tables to a hosted PostgreSQL database."""

from __future__ import annotations

import argparse
import os
from typing import Iterable, Mapping, Sequence

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from f1engine.db import PROJECT_ROOT, get_engine, run_schema


TABLES = (
    "events",
    "sessions",
    "drivers",
    "laps",
    "stints",
    "weather",
    "lap_telemetry_summary",
)
EXPORT_TABLES = TABLES
DEFAULT_MAX_MB = 400
DEFAULT_BATCH_SIZE = 1000


def load_local_env() -> None:
    """Load project .env without overriding variables supplied by the process."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def estimate_table_stats(
    engine: Engine, tables: Iterable[str] = TABLES
) -> dict[str, dict[str, int]]:
    """Estimate rows and physical size for known export tables."""
    stats: dict[str, dict[str, int]] = {}
    with engine.connect() as connection:
        for table_name in tables:
            if table_name not in TABLES:
                raise ValueError(f"Table is not in the hosted export allowlist: {table_name}")
            row_count = int(
                connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
            )
            size_bytes = int(
                connection.execute(
                    text(
                        "SELECT pg_total_relation_size("
                        "CAST(:table_name AS regclass))"
                    ),
                    {"table_name": table_name},
                ).scalar_one()
                or 0
            )
            stats[table_name] = {"rows": row_count, "size_bytes": size_bytes}
    return stats


def estimate_selected_table_size(
    engine: Engine, tables: Iterable[str] = TABLES
) -> tuple[int, int]:
    """Return (total size bytes, total rows) for the selected tables."""
    stats = estimate_table_stats(engine, tables)
    return (
        sum(item["size_bytes"] for item in stats.values()),
        sum(item["rows"] for item in stats.values()),
    )


def format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} bytes"


def print_stats(label: str, stats: Mapping[str, Mapping[str, int]]) -> None:
    print(label)
    total_rows = 0
    total_bytes = 0
    for table_name in TABLES:
        item = stats.get(table_name)
        if item is not None:
            rows = int(item["rows"])
            size_bytes = int(item["size_bytes"])
            total_rows += rows
            total_bytes += size_bytes
            print(f"  {table_name}: {rows} rows, {format_bytes(size_bytes)}")
    print(f"  TOTAL: {total_rows} rows, {format_bytes(total_bytes)}")


def fetch_table_rows(
    source_engine: Engine, table_name: str, batch_size: int = DEFAULT_BATCH_SIZE
) -> Iterable[list[dict]]:
    """Yield source rows in batches.  No rows from telemetry_samples are read."""
    if table_name not in TABLES:
        raise ValueError(f"Refusing to export non-allowlisted table: {table_name}")

    offset = 0
    while True:
        frame = pd.read_sql_query(
            text(
                f'SELECT * FROM "{table_name}" '
                f'ORDER BY 1 LIMIT :limit OFFSET :offset'
            ),
            source_engine,
            params={"limit": batch_size, "offset": offset},
        )
        if frame.empty:
            break
        yield (
            frame.astype(object)
            .where(pd.notna(frame), None)
            .to_dict(orient="records")
        )
        if len(frame) < batch_size:
            break
        offset += len(frame)


def copy_table(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Copy one allowlisted table, ignoring conflicts already present on target."""
    if table_name not in TABLES:
        raise ValueError(f"Refusing to export non-allowlisted table: {table_name}")

    table = Table(table_name, MetaData(), autoload_with=target_engine)
    copied = 0
    with target_engine.begin() as connection:
        for rows in fetch_table_rows(source_engine, table_name, batch_size):
            allowed = tuple(table.c.keys())
            clean_rows = [
                {key: row[key] for key in allowed if key in row} for row in rows
            ]
            if clean_rows:
                statement = insert(table).values(clean_rows).on_conflict_do_nothing()
                connection.execute(statement)
                copied += len(clean_rows)
    return copied


def copy_selected_tables(
    source_engine: Engine,
    target_engine: Engine,
    tables: Sequence[str] = TABLES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in tables:
        if table_name not in TABLES:
            raise ValueError(f"Refusing to export non-allowlisted table: {table_name}")
        counts[table_name] = copy_table(source_engine, target_engine, table_name, batch_size)
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export core F1 data to a hosted database")
    parser.add_argument(
        "--target-url-env",
        default="HOSTED_DATABASE_URL",
        help="Name of the environment variable containing the hosted database URL",
    )
    parser.add_argument(
        "--max-mb",
        "--max-size-mb",
        dest="max_mb",
        type=int,
        default=DEFAULT_MAX_MB,
        help="Refuse export when estimated source size exceeds this many MB",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_mb < 0:
        raise ValueError("--max-mb must be zero or greater")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be greater than zero")

    load_local_env()
    target_url = os.environ.get(args.target_url_env)
    if not target_url:
        raise RuntimeError(
            f"Hosted database URL is not set in environment variable {args.target_url_env}"
        )

    source_engine: Engine | None = None
    target_engine: Engine | None = None
    try:
        source_engine = get_engine()
        before = estimate_table_stats(source_engine)
        print_stats("Before copy (local source):", before)
        source_size = sum(item["size_bytes"] for item in before.values())
        if source_size > args.max_mb * 1024 * 1024:
            raise RuntimeError(
                f"Refusing export: estimated source size {format_bytes(source_size)} "
                f"exceeds the {args.max_mb} MB limit"
            )

        target_engine = create_engine(target_url, pool_pre_ping=True)
        run_schema(target_engine)
        destination_before = estimate_table_stats(target_engine)
        print_stats("Before copy (hosted target):", destination_before)

        copy_selected_tables(source_engine, target_engine, TABLES, args.batch_size)

        destination_after = estimate_table_stats(target_engine)
        print_stats("After copy (hosted target):", destination_after)
        return 0
    finally:
        if target_engine is not None:
            target_engine.dispose()
        if source_engine is not None:
            source_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
