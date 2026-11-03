"""Run a numbered SQL analysis query and print its result as a table."""

import argparse
from pathlib import Path
from typing import Any

from sqlalchemy import text

from f1engine.db import get_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_DIR = PROJECT_ROOT / "sql" / "queries"


def _format_table(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Render a small query result as a plain-text table."""
    formatted_rows = [
        [
            "NULL" if value is None else str(value)
            for value in row
        ]
        for row in rows
    ]
    widths = [
        max(
            len(column),
            *(len(row[index]) for row in formatted_rows),
        )
        for index, column in enumerate(columns)
    ]
    header = " | ".join(
        column.ljust(widths[index]) for index, column in enumerate(columns)
    )
    separator = "-+-".join("-" * width for width in widths)
    body = [
        " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(row)
        )
        for row in formatted_rows
    ]
    return "\n".join([header, separator, *body])


def run_query(query_number: int) -> int:
    """Execute one numbered query file and print at most its SQL result rows."""
    if not 1 <= query_number <= 10:
        raise ValueError("query_number must be between 1 and 10")

    query_path = QUERY_DIR / f"{query_number:02d}_"
    matches = list(QUERY_DIR.glob(f"{query_number:02d}_*.sql"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one query file matching {query_path.name}*.sql, "
            f"found {len(matches)}"
        )

    sql = matches[0].read_text(encoding="utf-8")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = [tuple(row) for row in result.fetchall()]
            columns = list(result.keys())
    finally:
        engine.dispose()

    print(f"Query {query_number:02d}: {matches[0].stem}")
    if not rows:
        print("(no rows)")
    else:
        print(_format_table(columns, rows))
        print(f"\n{len(rows)} row(s)")
    return len(rows)


def main() -> None:
    """Parse the query number from the command line."""
    parser = argparse.ArgumentParser(
        description="Run one numbered SQL analysis query"
    )
    parser.add_argument(
        "query_number",
        type=int,
        choices=range(1, 11),
        help="number of the SQL file to run, from 1 to 10",
    )
    args = parser.parse_args()
    run_query(args.query_number)


if __name__ == "__main__":
    main()
