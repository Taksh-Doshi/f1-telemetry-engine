"""Compare direct database execution with Valkey-cached degradation results."""

import math
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection

from f1engine.cache import cached_degradation_slopes, degradation_cache_key
from f1engine.db import get_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_PATH = PROJECT_ROOT / "sql" / "queries" / "10_degradation_slope_per_stint.sql"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "cache_benchmark.txt"
YEAR = 2024
CIRCUIT = "Bahrain Grand Prix"
COMPOUND = "SOFT"
RUNS = 50
TTL_SECONDS = 3600


def _query_degradation(connection: Connection) -> list[dict[str, Any]]:
    """Run the same filtered SQL query used by the cache-aside wrapper."""
    sql = QUERY_PATH.read_text(encoding="utf-8")
    result = connection.execute(
        text(sql),
        {
            "year": YEAR,
            "circuit": CIRCUIT,
            "compound": COMPOUND,
        },
    )
    return [dict(row) for row in result.mappings().all()]


def _measure_milliseconds(operation: Callable[[], Any]) -> float:
    """Run one operation and return its wall-clock duration in milliseconds."""
    started_at = time.perf_counter()
    operation()
    return (time.perf_counter() - started_at) * 1000


def _percentile_95(values: list[float]) -> float:
    """Return the nearest-rank 95th percentile for a non-empty sample."""
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def main() -> None:
    """Run the requested uncached, miss, and cached-hit measurements."""
    key = degradation_cache_key(YEAR, CIRCUIT, COMPOUND)
    engine = get_engine()
    try:
        from f1engine.cache import get_cache_client

        client = get_cache_client()
        client.delete(key)

        with engine.connect() as connection:

            def compute() -> list[dict[str, Any]]:
                return _query_degradation(connection)

            # Reuse one database connection so timings measure query work,
            # not the roughly ten-second connection startup on this machine.
            uncached_times = [
                _measure_milliseconds(compute)
                for _ in range(RUNS)
            ]
            miss_value: list[dict[str, Any]] | None = None

            def compute_once() -> list[dict[str, Any]]:
                nonlocal miss_value
                miss_value = compute()
                return miss_value

            miss_time = _measure_milliseconds(
                lambda: cached_degradation_slopes(
                    YEAR, CIRCUIT, COMPOUND, compute_once, ttl_seconds=TTL_SECONDS
                )
            )
            if miss_value is None:
                raise RuntimeError("The cache miss did not compute query results")

            hit_times: list[float] = []
            for _ in range(RUNS):
                hit_result: list[dict[str, Any]] | None = None

                def read_hit() -> None:
                    nonlocal hit_result
                    hit_result, status = cached_degradation_slopes(
                        YEAR,
                        CIRCUIT,
                        COMPOUND,
                        compute,
                        ttl_seconds=TTL_SECONDS,
                    )
                    if status != "hit":
                        raise RuntimeError(
                            "Expected a Valkey cache hit during benchmark, "
                            f"got {status!r}"
                        )

                hit_times.append(_measure_milliseconds(read_hit))
                if hit_result != miss_value:
                    raise RuntimeError("Cached results differ from the miss result")
    finally:
        engine.dispose()

    uncached_median = statistics.median(uncached_times)
    hit_median = statistics.median(hit_times)
    speed_up = uncached_median / hit_median if hit_median else float("inf")
    lines = [
        "Valkey degradation-query latency benchmark",
        f"Query selection: {YEAR}, {CIRCUIT}, {COMPOUND}",
        f"Cache key: {key}",
        f"Uncached database runs: {RUNS}",
        (
            "Uncached database median: "
            f"{uncached_median:.3f} ms"
        ),
        (
            "Uncached database p95: "
            f"{_percentile_95(uncached_times):.3f} ms"
        ),
        f"Cache miss run: {miss_time:.3f} ms",
        f"Cached hit runs: {RUNS}",
        f"Cached hit median: {hit_median:.3f} ms",
        f"Cached hit p95: {_percentile_95(hit_times):.3f} ms",
        f"Median speed-up (uncached / cached hit): {speed_up:.2f}x",
        f"Rows returned: {len(miss_value)}",
        (
            "Note: results are local to this machine and this dataset; "
            "the table contains 26,604 laps."
        ),
    ]
    output = "\n".join(lines) + "\n"
    print(output, end="")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
