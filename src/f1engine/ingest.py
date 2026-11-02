"""Load raw Formula 1 session data into Postgres."""

import argparse
from bisect import bisect_right
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import fastf1
import pandas as pd
from sqlalchemy import Engine, bindparam, text
from sqlalchemy.engine import Connection
from dotenv import load_dotenv

from f1engine.db import get_engine, run_schema


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)
VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}


def _is_missing(value: Any) -> bool:
    """Treat pandas and Python missing values consistently as SQL NULL."""
    if value is None:
        return True
    missing = pd.isna(value)
    return bool(missing)


def _clean_text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _seconds(value: Any) -> float | None:
    """Convert FastF1 duration values to seconds."""
    if _is_missing(value):
        return None
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    return float(value)


def _float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if _is_missing(value):
        return None
    result = int(value)
    if float(value) != result:
        raise ValueError(f"Expected a whole number, received {value!r}")
    return result


def _boolean(value: Any) -> bool | None:
    if _is_missing(value):
        return None
    return bool(value)


def _date(value: Any) -> date | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    raise TypeError(f"Expected a date-like value, received {value!r}")


def _datetime(value: Any) -> datetime | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    raise TypeError(f"Expected a datetime-like value, received {value!r}")


def _normalise_compound(
    value: Any, warned_unknowns: set[str]
) -> str | None:
    compound = _clean_text(value)
    if compound is None:
        return None

    normalised = compound.upper()
    if normalised in VALID_COMPOUNDS:
        return normalised

    if normalised not in warned_unknowns:
        LOGGER.warning("Unknown tyre compound %r; storing NULL", compound)
        warned_unknowns.add(normalised)
    return None


def _cache_directory() -> Path:
    """Enable FastF1's cache using the project-root-relative .env setting."""
    load_dotenv(PROJECT_ROOT / ".env")
    cache_dir = Path(os.getenv("FASTF1_CACHE_DIR", "cache"))
    if not cache_dir.is_absolute():
        cache_dir = PROJECT_ROOT / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.configure(cache_dir=str(cache_dir))
    return cache_dir


def _driver_records(session: Any, laps: pd.DataFrame) -> list[dict[str, Any]]:
    """Build one row per driver, including drivers with no recorded laps."""
    records_by_abbreviation: dict[str, dict[str, Any]] = {}
    results = session.results

    if results is not None and not results.empty:
        for result in results.to_dict("records"):
            abbreviation = _clean_text(result.get("Abbreviation"))
            if abbreviation is None:
                continue
            records_by_abbreviation[abbreviation] = {
                "abbreviation": abbreviation,
                "driver_number": _clean_text(result.get("DriverNumber")),
                "first_name": _clean_text(result.get("FirstName")),
                "last_name": _clean_text(result.get("LastName")),
                "full_name": _clean_text(result.get("FullName")),
                "country_code": _clean_text(result.get("CountryCode")),
            }

    # Laps are the source of truth for any driver missing from session.results.
    for lap in laps.to_dict("records"):
        abbreviation = _clean_text(lap.get("Driver"))
        if abbreviation is None:
            continue
        records_by_abbreviation.setdefault(
            abbreviation,
            {
                "abbreviation": abbreviation,
                "driver_number": _clean_text(lap.get("DriverNumber")),
                "first_name": None,
                "last_name": None,
                "full_name": None,
                "country_code": None,
            },
        )

    return list(records_by_abbreviation.values())


def _build_lap_records(
    laps: pd.DataFrame,
    session_id: int,
    driver_ids: dict[str, int],
) -> list[dict[str, Any]]:
    """Convert every FastF1 lap to one database row without filtering it."""
    records: list[dict[str, Any]] = []
    warned_unknowns: set[str] = set()

    for lap in laps.to_dict("records"):
        abbreviation = _clean_text(lap.get("Driver"))
        if abbreviation is None or abbreviation not in driver_ids:
            raise ValueError(
                f"Lap refers to driver {abbreviation!r}, but that driver "
                "could not be resolved"
            )

        lap_number = _integer(lap.get("LapNumber"))
        if lap_number is None or lap_number <= 0:
            raise ValueError(
                f"Lap for driver {abbreviation} has invalid lap number "
                f"{lap.get('LapNumber')!r}"
            )

        records.append(
            {
                "session_id": session_id,
                "driver_id": driver_ids[abbreviation],
                "lap_number": lap_number,
                "lap_time_seconds": _seconds(lap.get("LapTime")),
                "sector1_seconds": _seconds(lap.get("Sector1Time")),
                "sector2_seconds": _seconds(lap.get("Sector2Time")),
                "sector3_seconds": _seconds(lap.get("Sector3Time")),
                "speed_i1": _float(lap.get("SpeedI1")),
                "speed_i2": _float(lap.get("SpeedI2")),
                "speed_fl": _float(lap.get("SpeedFL")),
                "speed_st": _float(lap.get("SpeedST")),
                "compound": _normalise_compound(
                    lap.get("Compound"), warned_unknowns
                ),
                "tyre_life": _integer(lap.get("TyreLife")),
                "fresh_tyre": _boolean(lap.get("FreshTyre")),
                "stint_number": _integer(lap.get("Stint")),
                "position": _integer(lap.get("Position")),
                "track_status": (
                    None
                    if _is_missing(lap.get("TrackStatus"))
                    else str(lap.get("TrackStatus"))
                ),
                "is_personal_best": _boolean(lap.get("IsPersonalBest")),
                "is_accurate": _boolean(lap.get("IsAccurate")),
                "deleted": _boolean(lap.get("Deleted")),
                "deleted_reason": _clean_text(lap.get("DeletedReason")),
                "pit_in_time_seconds": _seconds(lap.get("PitInTime")),
                "pit_out_time_seconds": _seconds(lap.get("PitOutTime")),
                "team": _clean_text(lap.get("Team")),
            }
        )

    return records


def _build_stint_records(
    lap_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarise the laps into one stint row per driver and stint number."""
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for lap in lap_records:
        stint_number = lap["stint_number"]
        if stint_number is None:
            continue
        key = (lap["driver_id"], stint_number)
        grouped.setdefault(key, []).append(lap)

    records: list[dict[str, Any]] = []
    for (driver_id, stint_number), stint_laps in grouped.items():
        stint_laps.sort(key=lambda lap: lap["lap_number"])
        compound = next(
            (lap["compound"] for lap in stint_laps if lap["compound"] is not None),
            None,
        )
        fresh_tyre = next(
            (
                lap["fresh_tyre"]
                for lap in stint_laps
                if lap["fresh_tyre"] is not None
            ),
            None,
        )
        records.append(
            {
                "session_id": stint_laps[0]["session_id"],
                "driver_id": driver_id,
                "stint_number": stint_number,
                "start_lap": stint_laps[0]["lap_number"],
                "end_lap": stint_laps[-1]["lap_number"],
                "compound": compound,
                "tyre_age_at_start": stint_laps[0]["tyre_life"],
                "fresh_tyre": fresh_tyre,
            }
        )

    return records


def _build_lap_telemetry_summary(
    telemetry: pd.DataFrame,
    lap_start_time: Any,
    lap_duration: Any,
) -> dict[str, float | None]:
    """Summarise one driver's telemetry slice for a single lap."""
    empty_summary = {
        "top_speed": None,
        "mean_speed": None,
        "mean_throttle": None,
        "full_throttle_pct": None,
        "brake_pct": None,
        "drs_pct": None,
        "gear_changes": None,
    }
    if telemetry.empty or _is_missing(lap_start_time) or _is_missing(lap_duration):
        return empty_summary

    lap_start = pd.to_timedelta(lap_start_time)
    lap_end = lap_start + pd.to_timedelta(lap_duration)
    session_times = telemetry["SessionTime"]
    start_index = int(session_times.searchsorted(lap_start, side="left"))
    end_index = int(session_times.searchsorted(lap_end, side="left"))
    subset = telemetry.iloc[start_index:end_index]
    if subset.empty:
        return empty_summary

    speed = pd.to_numeric(subset["Speed"], errors="coerce")
    throttle = pd.to_numeric(subset["Throttle"], errors="coerce")
    brake = subset["Brake"].fillna(False).astype(bool)
    drs = pd.to_numeric(subset["DRS"], errors="coerce").fillna(0)
    gear = pd.to_numeric(subset["nGear"], errors="coerce")

    return {
        "top_speed": float(speed.max()) if speed.notna().any() else None,
        "mean_speed": float(speed.mean()) if speed.notna().any() else None,
        "mean_throttle": float(throttle.mean()) if throttle.notna().any() else None,
        "full_throttle_pct": float(
            (throttle.ge(100).mean() * 100) if throttle.notna().any() else None
        ),
        "brake_pct": float(
            (brake.mean() * 100) if not brake.empty else None
        ),
        "drs_pct": float(
            (drs.ge(10).mean() * 100) if drs.notna().any() else None
        ),
        "gear_changes": float(
            (gear.diff().fillna(0).ne(0).sum())
            if gear.notna().any()
            else None
        ),
    }


def _persist_lap_summaries(
    connection: Connection,
    f1_session: Any,
    session_id: int,
) -> int:
    """Summarise each stored lap using each driver's loaded car data once."""
    stored_laps = connection.execute(
        text(
            "SELECT l.lap_id, l.lap_number, d.abbreviation "
            "FROM laps AS l "
            "JOIN drivers AS d ON d.driver_id = l.driver_id "
            "WHERE l.session_id = :session_id"
        ),
        {"session_id": session_id},
    ).mappings().all()
    if not stored_laps:
        return 0

    lap_ids = {
        (row["abbreviation"], int(row["lap_number"])): int(row["lap_id"])
        for row in stored_laps
    }
    laps_by_driver: dict[str, list[dict[str, Any]]] = {}
    for lap in f1_session.laps.to_dict("records"):
        abbreviation = _clean_text(lap.get("Driver"))
        if abbreviation is not None:
            laps_by_driver.setdefault(abbreviation, []).append(lap)

    telemetry_by_driver: dict[str, pd.DataFrame] = {}
    for driver_number, car_data in f1_session.car_data.items():
        driver = f1_session.get_driver(driver_number)
        abbreviation = _clean_text(getattr(driver, "Abbreviation", None))
        if abbreviation is None or car_data.empty:
            continue

        telemetry = car_data.copy()
        telemetry["SessionTime"] = pd.to_timedelta(
            telemetry["SessionTime"], errors="coerce"
        )
        telemetry = telemetry.dropna(subset=["SessionTime"]).sort_values(
            "SessionTime"
        )
        for column in ("Speed", "Throttle", "DRS", "nGear"):
            telemetry[column] = pd.to_numeric(telemetry[column], errors="coerce")
        telemetry["Brake"] = telemetry["Brake"].fillna(False).astype(bool)
        telemetry_by_driver[abbreviation] = telemetry

    summary_columns = (
        "top_speed",
        "mean_speed",
        "mean_throttle",
        "full_throttle_pct",
        "brake_pct",
        "drs_pct",
        "gear_changes",
    )
    records: list[dict[str, Any]] = []
    for abbreviation, driver_laps in laps_by_driver.items():
        telemetry = telemetry_by_driver.get(abbreviation, pd.DataFrame())
        for lap in driver_laps:
            lap_number = _integer(lap.get("LapNumber"))
            if lap_number is None:
                continue
            lap_id = lap_ids.get((abbreviation, lap_number))
            if lap_id is None:
                continue

            summary = _build_lap_telemetry_summary(
                telemetry,
                lap.get("LapStartTime"),
                lap.get("LapTime"),
            )
            records.append({"lap_id": lap_id, **summary})

    # Refresh derived values on reruns, then insert any missing lap summaries.
    if records:
        connection.execute(
            text(
                "UPDATE lap_telemetry_summary SET "
                "top_speed = :top_speed, "
                "mean_speed = :mean_speed, "
                "mean_throttle = :mean_throttle, "
                "full_throttle_pct = :full_throttle_pct, "
                "brake_pct = :brake_pct, "
                "drs_pct = :drs_pct, "
                "gear_changes = :gear_changes "
                "WHERE lap_id = :lap_id"
            ),
            records,
        )

    _insert_many(
        connection,
        "lap_telemetry_summary",
        ("lap_id", *summary_columns),
        ("lap_id",),
        records,
    )
    return len(records)


def _build_telemetry_sample_records(
    car_data: pd.DataFrame,
    position_data: pd.DataFrame,
    lap_data: pd.DataFrame,
    session_id: int,
    driver_id: int,
    stored_lap_numbers: set[int],
) -> list[dict[str, Any]]:
    """Align one driver's car and position samples and attach a lap number."""
    if car_data.empty or lap_data.empty or not stored_lap_numbers:
        return []

    car_columns = (
        "Speed",
        "Throttle",
        "Brake",
        "nGear",
        "RPM",
        "DRS",
    )
    car = car_data.copy()
    car["SessionTime"] = pd.to_timedelta(car["SessionTime"], errors="coerce")
    car = car.dropna(subset=["SessionTime"]).sort_values("SessionTime")
    for column in ("Speed", "Throttle", "nGear", "RPM", "DRS"):
        car[column] = pd.to_numeric(car[column], errors="coerce")
    car["Brake"] = car["Brake"].fillna(False).astype(bool)
    car = car[["SessionTime", *car_columns]]

    if position_data.empty:
        car["X"] = None
        car["Y"] = None
    else:
        position = position_data.copy()
        position["SessionTime"] = pd.to_timedelta(
            position["SessionTime"], errors="coerce"
        )
        position = position.dropna(subset=["SessionTime"]).sort_values(
            "SessionTime"
        )
        position["X"] = pd.to_numeric(position["X"], errors="coerce")
        position["Y"] = pd.to_numeric(position["Y"], errors="coerce")
        car = pd.merge_asof(
            car,
            position[["SessionTime", "X", "Y"]],
            on="SessionTime",
            direction="nearest",
            tolerance=pd.Timedelta(milliseconds=500),
        )

    lap_starts: list[tuple[int, int]] = []
    for lap in lap_data.to_dict("records"):
        lap_number = _integer(lap.get("LapNumber"))
        lap_start = lap.get("LapStartTime")
        if (
            lap_number is None
            or lap_number not in stored_lap_numbers
            or _is_missing(lap_start)
        ):
            continue
        lap_starts.append((int(pd.to_timedelta(lap_start).value), lap_number))

    lap_starts.sort()
    if not lap_starts:
        return []

    starts = [start for start, _ in lap_starts]
    records: list[dict[str, Any]] = []
    for sample in car.to_dict("records"):
        sample_time = sample["SessionTime"]
        lap_index = bisect_right(starts, int(sample_time.value)) - 1
        if lap_index < 0:
            continue
        lap_number = lap_starts[lap_index][1]
        records.append(
            {
                "session_id": session_id,
                "driver_id": driver_id,
                "lap_number": lap_number,
                "time_seconds": float(sample_time.total_seconds()),
                "speed": _float(sample.get("Speed")),
                "throttle": _float(sample.get("Throttle")),
                "brake": _boolean(sample.get("Brake")),
                "gear": _integer(sample.get("nGear")),
                "rpm": _integer(sample.get("RPM")),
                "drs": _integer(sample.get("DRS")),
                "x": _float(sample.get("X")),
                "y": _float(sample.get("Y")),
            }
        )
    return records


def ingest_telemetry_samples(
    year: int,
    round_number: int,
    session_type: str = "R",
    drivers: list[str] | None = None,
) -> int:
    """Store raw car telemetry samples for one session and selected drivers."""
    if year <= 0:
        raise ValueError("year must be a positive integer")
    if round_number <= 0:
        raise ValueError("round_number must be a positive integer")
    if not session_type.strip():
        raise ValueError("session_type cannot be empty")
    if drivers is not None and not drivers:
        raise ValueError("drivers must contain at least one abbreviation or number")

    normalised_session_type = session_type.strip().upper()
    requested_drivers = (
        {driver.strip().upper() for driver in drivers if driver.strip()}
        if drivers is not None
        else None
    )
    if requested_drivers is not None and not requested_drivers:
        raise ValueError("drivers must contain at least one abbreviation or number")

    engine = get_engine()
    try:
        run_schema(engine)
        with engine.connect() as connection:
            session_id = connection.execute(
                text(
                    "SELECT s.session_id FROM sessions AS s "
                    "JOIN events AS e ON e.event_id = s.event_id "
                    "WHERE e.season_year = :year "
                    "AND e.round_number = :round_number "
                    "AND s.session_type = :session_type"
                ),
                {
                    "year": year,
                    "round_number": round_number,
                    "session_type": normalised_session_type,
                },
            ).scalar_one_or_none()
            if session_id is None:
                raise ValueError(
                    f"No stored {normalised_session_type} session for "
                    f"{year} round {round_number}; ingest the session first"
                )

            stored_laps = connection.execute(
                text(
                    "SELECT d.driver_id, d.abbreviation, l.lap_number "
                    "FROM laps AS l "
                    "JOIN drivers AS d ON d.driver_id = l.driver_id "
                    "WHERE l.session_id = :session_id"
                ),
                {"session_id": session_id},
            ).mappings().all()
    finally:
        engine.dispose()

    if not stored_laps:
        raise ValueError(
            f"No stored laps for {year} round {round_number}; ingest the session first"
        )

    _cache_directory()
    f1_session = fastf1.get_session(year, round_number, normalised_session_type)
    f1_session.load(telemetry=True, messages=False, weather=False)

    stored_driver_ids: dict[str, int] = {}
    stored_lap_numbers_by_driver: dict[str, set[int]] = {}
    for lap in stored_laps:
        abbreviation = str(lap["abbreviation"]).upper()
        stored_driver_ids[abbreviation] = int(lap["driver_id"])
        stored_lap_numbers_by_driver.setdefault(abbreviation, set()).add(
            int(lap["lap_number"])
        )

    available_drivers: dict[str, str] = {}
    abbreviation_by_number: dict[str, str] = {}
    for driver_number in f1_session.car_data:
        driver = f1_session.get_driver(driver_number)
        abbreviation = _clean_text(driver.get("Abbreviation"))
        number = _clean_text(driver.get("DriverNumber"))
        if abbreviation is None:
            continue
        abbreviation = abbreviation.upper()
        available_drivers[abbreviation] = driver_number
        if number is not None:
            abbreviation_by_number[number.upper()] = abbreviation

    if requested_drivers is None:
        selected_abbreviations = list(available_drivers)
    else:
        selected_abbreviations = []
        unmatched: list[str] = []
        for requested in sorted(requested_drivers):
            abbreviation = requested
            if abbreviation not in available_drivers:
                abbreviation = abbreviation_by_number.get(requested, "")
            if not abbreviation:
                unmatched.append(requested)
            else:
                selected_abbreviations.append(abbreviation)
        if unmatched:
            raise ValueError(
                "Could not match requested driver(s): "
                f"{', '.join(unmatched)}. Use a FastF1 abbreviation "
                "(for example VER) or driver number."
            )

    selected_abbreviations = list(dict.fromkeys(selected_abbreviations))
    missing_stored_laps = [
        abbreviation
        for abbreviation in selected_abbreviations
        if abbreviation not in stored_driver_ids
    ]
    if missing_stored_laps:
        raise ValueError(
            "No stored laps for requested driver(s): "
            f"{', '.join(missing_stored_laps)}; ingest the session first"
        )

    fastf1_laps_by_driver: dict[str, list[dict[str, Any]]] = {}
    for lap in f1_session.laps.to_dict("records"):
        abbreviation = _clean_text(lap.get("Driver"))
        if abbreviation is not None:
            fastf1_laps_by_driver.setdefault(abbreviation.upper(), []).append(lap)

    partition_name = f"telemetry_samples_session_{int(session_id)}"
    insert_columns = (
        "session_id",
        "driver_id",
        "lap_number",
        "time_seconds",
        "speed",
        "throttle",
        "brake",
        "gear",
        "rpm",
        "drs",
        "x",
        "y",
    )
    with engine.begin() as connection:
        # session_id is a database-generated integer, so it is safe in this DDL.
        connection.exec_driver_sql(
            f"CREATE TABLE IF NOT EXISTS {partition_name} "
            "PARTITION OF telemetry_samples "
            f"FOR VALUES IN ({int(session_id)})"
        )

        for abbreviation in selected_abbreviations:
            driver_number = available_drivers[abbreviation]
            car_data = f1_session.car_data[driver_number]
            position_data = f1_session.pos_data.get(
                driver_number,
                pd.DataFrame(columns=["SessionTime", "X", "Y"]),
            )
            sample_records = _build_telemetry_sample_records(
                car_data,
                position_data,
                pd.DataFrame(fastf1_laps_by_driver.get(abbreviation, [])),
                int(session_id),
                stored_driver_ids[abbreviation],
                stored_lap_numbers_by_driver[abbreviation],
            )
            for offset in range(0, len(sample_records), 5000):
                _insert_many(
                    connection,
                    "telemetry_samples",
                    insert_columns,
                    ("session_id", "driver_id", "time_seconds"),
                    sample_records[offset : offset + 5000],
                )

    selected_driver_ids = [
        stored_driver_ids[abbreviation]
        for abbreviation in selected_abbreviations
    ]
    count_engine = get_engine()
    try:
        with count_engine.connect() as connection:
            sample_count = connection.execute(
                text(
                    "SELECT count(*) FROM telemetry_samples "
                    "WHERE session_id = :session_id "
                    "AND driver_id IN :driver_ids"
                ).bindparams(bindparam("driver_ids", expanding=True)),
                {"session_id": session_id, "driver_ids": selected_driver_ids},
            ).scalar_one()
    finally:
        count_engine.dispose()

    LOGGER.info(
        "Stored %s telemetry samples for %s round %s drivers %s "
        "in partition %s",
        sample_count,
        year,
        round_number,
        ", ".join(selected_abbreviations),
        partition_name,
    )
    return int(sample_count)


def _scheduled_start(event: Any, session_name: str) -> datetime | None:
    """Find the matching UTC start time in FastF1's event schedule."""
    for session_number in range(1, 6):
        scheduled_name = _clean_text(event.get(f"Session{session_number}"))
        if scheduled_name and scheduled_name.casefold() == session_name.casefold():
            return _datetime(event.get(f"Session{session_number}DateUtc"))
    return None


def _insert_many(
    connection: Connection,
    table: str,
    columns: tuple[str, ...],
    conflict_columns: tuple[str, ...],
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return

    column_sql = ", ".join(columns)
    value_sql = ", ".join(f":{column}" for column in columns)
    conflict_sql = ", ".join(conflict_columns)
    statement = text(
        f"INSERT INTO {table} ({column_sql}) "
        f"VALUES ({value_sql}) "
        f"ON CONFLICT ({conflict_sql}) DO NOTHING"
    )
    connection.execute(statement, records)


def _persist_session(
    engine: Engine,
    year: int,
    round_number: int,
    session_type: str,
    f1_session: Any,
) -> int:
    """Insert a loaded FastF1 session in foreign-key order."""
    event = f1_session.event
    laps = f1_session.laps
    weather = f1_session.weather_data
    session_name = str(f1_session.name)

    event_name = _clean_text(event.get("EventName"))
    if event_name is None:
        raise ValueError("FastF1 event is missing its EventName")

    driver_records = _driver_records(f1_session, laps)
    with engine.begin() as connection:
        _insert_many(
            connection,
            "events",
            (
                "season_year",
                "round_number",
                "event_name",
                "official_event_name",
                "country",
                "location",
                "event_format",
                "event_date",
            ),
            ("season_year", "round_number"),
            [
                {
                    "season_year": year,
                    "round_number": round_number,
                    "event_name": event_name,
                    "official_event_name": _clean_text(
                        event.get("OfficialEventName")
                    ),
                    "country": _clean_text(event.get("Country")),
                    "location": _clean_text(event.get("Location")),
                    "event_format": _clean_text(event.get("EventFormat")),
                    "event_date": _date(event.get("EventDate")),
                }
            ],
        )
        event_id = connection.execute(
            text(
                "SELECT event_id FROM events "
                "WHERE season_year = :year AND round_number = :round_number"
            ),
            {"year": year, "round_number": round_number},
        ).scalar_one()

        _insert_many(
            connection,
            "sessions",
            (
                "event_id",
                "session_name",
                "session_type",
                "start_time",
                "end_time",
            ),
            ("event_id", "session_type"),
            [
                {
                    "event_id": event_id,
                    "session_name": session_name,
                    "session_type": session_type,
                    "start_time": _scheduled_start(event, session_name),
                    "end_time": None,
                }
            ],
        )
        session_id = connection.execute(
            text(
                "SELECT session_id FROM sessions "
                "WHERE event_id = :event_id AND session_type = :session_type"
            ),
            {"event_id": event_id, "session_type": session_type},
        ).scalar_one()

        _insert_many(
            connection,
            "drivers",
            (
                "abbreviation",
                "driver_number",
                "first_name",
                "last_name",
                "full_name",
                "country_code",
            ),
            ("abbreviation",),
            driver_records,
        )

        abbreviations = [record["abbreviation"] for record in driver_records]
        driver_ids: dict[str, int] = {}
        if abbreviations:
            driver_id_statement = text(
                "SELECT abbreviation, driver_id FROM drivers "
                "WHERE abbreviation IN :abbreviations"
            ).bindparams(bindparam("abbreviations", expanding=True))
            driver_ids = {
                row.abbreviation: row.driver_id
                for row in connection.execute(
                    driver_id_statement, {"abbreviations": abbreviations}
                )
            }

        lap_records = _build_lap_records(laps, session_id, driver_ids)
        _insert_many(
            connection,
            "laps",
            (
                "session_id",
                "driver_id",
                "lap_number",
                "lap_time_seconds",
                "sector1_seconds",
                "sector2_seconds",
                "sector3_seconds",
                "speed_i1",
                "speed_i2",
                "speed_fl",
                "speed_st",
                "compound",
                "tyre_life",
                "fresh_tyre",
                "stint_number",
                "position",
                "track_status",
                "is_personal_best",
                "is_accurate",
                "deleted",
                "deleted_reason",
                "pit_in_time_seconds",
                "pit_out_time_seconds",
                "team",
            ),
            ("session_id", "driver_id", "lap_number"),
            lap_records,
        )

        stint_records = _build_stint_records(lap_records)
        _insert_many(
            connection,
            "stints",
            (
                "session_id",
                "driver_id",
                "stint_number",
                "start_lap",
                "end_lap",
                "compound",
                "tyre_age_at_start",
                "fresh_tyre",
            ),
            ("session_id", "driver_id", "stint_number"),
            stint_records,
        )

        weather_records: list[dict[str, Any]] = []
        if weather is not None:
            for record in weather.to_dict("records"):
                time_seconds = _seconds(record.get("Time"))
                if time_seconds is None:
                    raise ValueError(
                        "FastF1 weather row is missing its required Time value"
                    )
                weather_records.append(
                    {
                        "session_id": session_id,
                        "time_seconds": time_seconds,
                        "air_temp": _float(record.get("AirTemp")),
                        "track_temp": _float(record.get("TrackTemp")),
                        "humidity": _float(record.get("Humidity")),
                        "pressure": _float(record.get("Pressure")),
                        "rainfall": _boolean(record.get("Rainfall")),
                        "wind_direction": _integer(record.get("WindDirection")),
                        "wind_speed": _float(record.get("WindSpeed")),
                    }
                )
        _insert_many(
            connection,
            "weather",
            (
                "session_id",
                "time_seconds",
                "air_temp",
                "track_temp",
                "humidity",
                "pressure",
                "rainfall",
                "wind_direction",
                "wind_speed",
            ),
            ("session_id", "time_seconds"),
            weather_records,
        )

        summary_count = _persist_lap_summaries(
            connection,
            f1_session,
            session_id,
        )
        LOGGER.info(
            "Prepared %s lap telemetry summaries for %s",
            summary_count,
            session_name,
        )

        return int(
            connection.execute(
                text("SELECT count(*) FROM laps WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).scalar_one()
        )


def ingest_session(
    year: int, round: int, session_type: str = "R"
) -> int:
    """Load one session, then return its total stored lap count."""
    if year <= 0:
        raise ValueError("year must be a positive integer")
    if round <= 0:
        raise ValueError("round must be a positive integer")
    if not session_type.strip():
        raise ValueError("session_type cannot be empty")

    normalised_session_type = session_type.strip().upper()
    _cache_directory()

    # Car telemetry is loaded so lap summaries are saved with the raw session.
    f1_session = fastf1.get_session(year, round, normalised_session_type)
    f1_session.load(
        telemetry=True,
        messages=False,
        weather=True,
    )

    engine = get_engine()
    try:
        run_schema(engine)
        lap_count = _persist_session(
            engine,
            year,
            round,
            normalised_session_type,
            f1_session,
        )
    finally:
        engine.dispose()

    LOGGER.info(
        "Stored %s total laps for %s %s, %s",
        lap_count,
        year,
        round,
        f1_session.name,
    )
    return lap_count


def _stored_ingest_counts(
    engine: Engine, year: int, round_number: int, session_type: str
) -> tuple[int, int]:
    """Return stored lap and summary counts for one session."""
    statement = text(
        "SELECT count(l.lap_id), count(summary.lap_id) "
        "FROM events AS e "
        "JOIN sessions AS s ON s.event_id = e.event_id "
        "LEFT JOIN laps AS l ON l.session_id = s.session_id "
        "LEFT JOIN lap_telemetry_summary AS summary "
        "ON summary.lap_id = l.lap_id "
        "WHERE e.season_year = :year "
        "AND e.round_number = :round_number "
        "AND s.session_type = :session_type"
    )
    with engine.connect() as connection:
        row = connection.execute(
            statement,
            {
                "year": year,
                "round_number": round_number,
                "session_type": session_type,
            },
        ).one()
        return int(row[0]), int(row[1])


def ingest_lap_summaries(
    year: int,
    round_number: int,
    session_type: str = "R",
) -> int:
    """Compatibility wrapper; normal session ingestion also creates summaries."""
    return ingest_session(year, round_number, session_type)


def ingest_season(year: int) -> dict[str, Any]:
    """Ingest every non-testing race in a season and summarize the outcome."""
    if year <= 0:
        raise ValueError("year must be a positive integer")

    _cache_directory()
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    rounds: list[int] = []
    for _, event in schedule.iterrows():
        round_number = _integer(event.get("RoundNumber"))
        if round_number is None or round_number <= 0:
            LOGGER.info(
                "Skipping schedule entry without a valid race round: %s",
                _clean_text(event.get("EventName")) or "unnamed event",
            )
            continue
        rounds.append(round_number)

    succeeded: list[int] = []
    failed: list[dict[str, Any]] = []
    total_laps = 0

    engine = get_engine()
    try:
        # Ensure schema exists before checking what has already been ingested.
        run_schema(engine)
        for index, round_number in enumerate(rounds):
            try:
                existing_laps, existing_summaries = _stored_ingest_counts(
                    engine, year, round_number, "R"
                )
                if (
                    existing_laps > 0
                    and existing_summaries == existing_laps
                ):
                    LOGGER.info(
                        "Skipping %s round %s: already stored %s laps "
                        "and summaries",
                        year,
                        round_number,
                        existing_laps,
                    )
                    lap_count = existing_laps
                else:
                    if existing_laps > 0:
                        LOGGER.info(
                            "Reprocessing %s round %s to fill missing telemetry "
                            "summaries (%s laps, %s summaries)",
                            year,
                            round_number,
                            existing_laps,
                            existing_summaries,
                        )
                    lap_count = ingest_session(year, round_number, "R")

                succeeded.append(round_number)
                total_laps += lap_count
            except Exception as error:
                LOGGER.exception(
                    "Failed to ingest %s round %s; continuing with the next race",
                    year,
                    round_number,
                )
                failed.append(
                    {
                        "round": round_number,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )

            if index < len(rounds) - 1:
                time.sleep(2)
    finally:
        engine.dispose()

    summary = {
        "year": year,
        "rounds_succeeded": len(succeeded),
        "rounds_failed": len(failed),
        "successful_round_numbers": succeeded,
        "failed_rounds": failed,
        "total_laps": total_laps,
    }
    LOGGER.info(
        "Season %s summary: %s rounds succeeded, %s failed, %s total laps",
        year,
        summary["rounds_succeeded"],
        summary["rounds_failed"],
        total_laps,
    )
    return summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Ingest Formula 1 session data")
    parser.add_argument("year", type=int, nargs="?")
    parser.add_argument("round_number", type=int, nargs="?")
    parser.add_argument("session_type", nargs="?", default="R")
    parser.add_argument(
        "--season",
        type=int,
        help="ingest every race round in the given year",
    )
    parser.add_argument(
        "--telemetry-samples",
        action="store_true",
        help="store raw telemetry samples for one session",
    )
    parser.add_argument(
        "--drivers",
        help="comma-separated driver abbreviations or numbers for raw telemetry",
    )
    args = parser.parse_args()

    if args.season is not None:
        if (
            args.year is not None
            or args.round_number is not None
            or args.telemetry_samples
            or args.drivers is not None
        ):
            parser.error(
                "--season cannot be combined with positional arguments, "
                "--telemetry-samples, or --drivers"
            )
        ingest_season(args.season)
    elif args.year is None or args.round_number is None:
        parser.error("provide YEAR ROUND [SESSION_TYPE] or --season YEAR")
    elif args.drivers is not None and not args.telemetry_samples:
        parser.error("--drivers requires --telemetry-samples")
    elif args.telemetry_samples:
        selected_drivers = (
            [driver.strip() for driver in args.drivers.split(",")]
            if args.drivers is not None
            else None
        )
        if selected_drivers is not None and any(not driver for driver in selected_drivers):
            parser.error("--drivers must be a comma-separated list without empty entries")
        ingest_telemetry_samples(
            args.year,
            args.round_number,
            args.session_type,
            selected_drivers,
        )
    else:
        ingest_session(args.year, args.round_number, args.session_type)


if __name__ == "__main__":
    main()
