"""Run a numbered SQL analysis query and print its result as a table."""

import argparse
from pathlib import Path
from typing import Any

from sqlalchemy import text

from f1engine.cache import cached_degradation_slopes
from f1engine.db import get_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_DIR = PROJECT_ROOT / "sql" / "queries"
DEGRADATION_TTL_SECONDS = 3600


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
            if query_number == 10:
                result = connection.execute(
                    text(sql),
                    {"year": None, "circuit": None, "compound": None},
                )
            else:
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


def _load_degradation_rows(
    year: int | None,
    circuit: str | None,
    compound: str | None,
) -> tuple[list[dict[str, Any]], str]:
    """Run the degradation query and cache results for a specific selection."""
    query_path = QUERY_DIR / "10_degradation_slope_per_stint.sql"
    sql = query_path.read_text(encoding="utf-8")
    parameters = {
        "year": year,
        "circuit": circuit,
        "compound": compound.upper() if compound is not None else None,
    }

    def compute() -> list[dict[str, Any]]:
        engine = get_engine()
        try:
            with engine.connect() as connection:
                result = connection.execute(text(sql), parameters)
                return [dict(row) for row in result.mappings().all()]
        finally:
            engine.dispose()

    return cached_degradation_slopes(
        year if year is not None else 0,
        circuit if circuit is not None else "all",
        compound if compound is not None else "all",
        compute,
        ttl_seconds=DEGRADATION_TTL_SECONDS,
    )


def run_cached_degradation_query(
    year: int,
    circuit: str,
    compound: str,
) -> tuple[int, str]:
    """Print the degradation analysis for one circuit and tyre compound."""
    if year <= 0:
        raise ValueError("year must be a positive integer")
    if not circuit.strip():
        raise ValueError("circuit cannot be empty")
    if not compound.strip():
        raise ValueError("compound cannot be empty")

    rows, cache_status = _load_degradation_rows(
        year,
        circuit.strip(),
        compound.strip(),
    )
    print(
        "Cache key: "
        f"f1:deg:{year}:{circuit.strip()}:{compound.strip().upper()}"
    )
    print(f"Cache status: {cache_status}")
    if not rows:
        print("(no rows)")
    else:
        columns = list(rows[0])
        print(_format_table(columns, [tuple(row.values()) for row in rows]))
        print(f"\n{len(rows)} row(s)")
    return len(rows), cache_status


def main() -> None:
    """Parse the query number from the command line."""
    parser = argparse.ArgumentParser(
        description="Run one numbered SQL analysis query"
    )
    parser.add_argument(
        "--degradation",
        nargs=3,
        metavar=("YEAR", "CIRCUIT", "COMPOUND"),
        help="run the cached degradation query for a year, circuit, and compound",
    )
    parser.add_argument(
        "query_number",
        type=int,
        choices=range(1, 11),
        nargs="?",
        help="number of the SQL file to run, from 1 to 10",
    )
    args = parser.parse_args()
    if args.degradation is not None:
        if args.query_number is not None:
            parser.error("--degradation cannot be combined with a query number")
        year_text, circuit, compound = args.degradation
        try:
            year = int(year_text)
        except ValueError:
            parser.error("YEAR in --degradation must be an integer")
        run_cached_degradation_query(year, circuit, compound)
    elif args.query_number is None:
        parser.error("provide a query number or --degradation YEAR CIRCUIT COMPOUND")
    else:
        run_query(args.query_number)


if __name__ == "__main__":
    main()
