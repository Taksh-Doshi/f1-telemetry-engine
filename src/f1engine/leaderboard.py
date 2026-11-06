"""Maintain and replay race leaderboards in Valkey sorted sets."""

import argparse
import itertools
import logging
import math
import time
from typing import Any

from sqlalchemy import text

from f1engine.cache import get_cache_client
from f1engine.db import get_engine


LOGGER = logging.getLogger(__name__)
REPLAY_SLEEP_SECONDS = 0.02


def leaderboard_key(year: int, round_number: int) -> str:
    """Build the sorted-set key for one race."""
    if year <= 0 or round_number <= 0:
        raise ValueError("year and round_number must be positive integers")
    return f"f1:leaderboard:{year}:{round_number}"


def update_from_lap(
    year: int,
    round_number: int,
    driver_code: str,
    lap_time_seconds: float,
) -> bool:
    """Keep the driver's fastest lap, never replacing it with a slower time."""
    if not driver_code.strip():
        raise ValueError("driver_code cannot be empty")
    lap_time = float(lap_time_seconds)
    if not math.isfinite(lap_time) or lap_time <= 0:
        raise ValueError("lap_time_seconds must be a positive finite number")

    client = get_cache_client()
    # LT means Valkey updates an existing driver only when the new time is lower.
    changed = client.zadd(
        leaderboard_key(year, round_number),
        {driver_code.strip().upper(): lap_time},
        lt=True,
        ch=True,
    )
    return bool(changed)


def top_n(
    year: int,
    round_number: int,
    n: int = 5,
) -> list[tuple[str, float]]:
    """Return the fastest drivers and lap times using ZRANGE with scores."""
    if n <= 0:
        raise ValueError("n must be a positive integer")
    values = get_cache_client().zrange(
        leaderboard_key(year, round_number),
        0,
        n - 1,
        withscores=True,
    )
    return [(str(driver), float(score)) for driver, score in values]


def rank_of(year: int, round_number: int, driver_code: str) -> int | None:
    """Return a driver's zero-based sorted-set rank, or None if absent."""
    if not driver_code.strip():
        raise ValueError("driver_code cannot be empty")
    rank = get_cache_client().zrank(
        leaderboard_key(year, round_number),
        driver_code.strip().upper(),
    )
    return int(rank) if rank is not None else None


def _print_leaderboard(
    year: int,
    round_number: int,
    lap_number: int,
) -> None:
    """Print the current five fastest drivers in race order."""
    print(f"\nAfter lap {lap_number}, top 5:")
    leaders = top_n(year, round_number, 5)
    if not leaders:
        print("(no valid laps yet)")
        return
    for position, (driver_code, lap_time) in enumerate(leaders, start=1):
        print(f"{position}. {driver_code}: {lap_time:.3f}s")


def replay_race(year: int, round_number: int) -> int:
    """Replay clean race laps into the leaderboard, printing every tenth lap."""
    if year <= 0 or round_number <= 0:
        raise ValueError("year and round_number must be positive integers")

    statement = text(
        "SELECT lap_number, driver_code, lap_time_seconds "
        "FROM clean_laps "
        "WHERE year = :year "
        "AND round = :round_number "
        "AND session_type = 'R' "
        "AND lap_time_seconds > 0 "
        "ORDER BY lap_number, driver_code"
    )
    engine = get_engine()
    try:
        with engine.connect() as connection:
            laps = connection.execute(
                statement,
                {"year": year, "round_number": round_number},
            ).mappings().all()
    finally:
        engine.dispose()

    if not laps:
        raise ValueError(
            f"No clean race laps found for {year} round {round_number}"
        )

    key = leaderboard_key(year, round_number)
    # Clear this derived race key so the replay visibly builds from lap one.
    get_cache_client().delete(key)
    print(f"Replaying {len(laps)} clean laps into {key}")

    last_lap_number = 0
    for lap_number, lap_group in itertools.groupby(
        laps, key=lambda row: int(row["lap_number"])
    ):
        for lap in lap_group:
            update_from_lap(
                year,
                round_number,
                str(lap["driver_code"]),
                float(lap["lap_time_seconds"]),
            )
        last_lap_number = lap_number
        if lap_number % 10 == 0:
            _print_leaderboard(year, round_number, lap_number)
        time.sleep(REPLAY_SLEEP_SECONDS)

    if last_lap_number % 10 != 0:
        _print_leaderboard(year, round_number, last_lap_number)
    print(f"\nReplay complete: {len(laps)} clean lap records processed")
    return len(laps)


def main() -> None:
    """Replay one race specified as YEAR ROUND."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Replay clean laps into a Valkey race leaderboard"
    )
    parser.add_argument("year", type=int)
    parser.add_argument("round_number", type=int)
    args = parser.parse_args()
    replay_race(args.year, args.round_number)


if __name__ == "__main__":
    main()
