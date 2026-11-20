"""Database integration checks using a transactionally rolled-back fixture."""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from f1engine.db import get_engine
from f1engine.ingest import _build_lap_records, _insert_many


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lap_fixture.csv"
LAP_COLUMNS = (
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
)


@pytest.mark.integration
def test_fixture_ingest_is_idempotent_and_clean_view_filters_rows():
    fixture = pd.read_csv(FIXTURE_PATH)
    fixture["LapTime"] = pd.to_timedelta(fixture["LapTimeSeconds"], unit="s")
    fixture["PitInTime"] = pd.to_timedelta(fixture["PitInSeconds"], unit="s")
    fixture["PitOutTime"] = pd.to_timedelta(fixture["PitOutSeconds"], unit="s")

    engine = get_engine()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            existing_abbreviations = set(
                connection.execute(text("SELECT abbreviation FROM drivers")).scalars()
            )
            synthetic_abbreviations = [
                f"Q{index:02X}"
                for index in range(256)
                if f"Q{index:02X}" not in existing_abbreviations
            ][:4]
            assert len(synthetic_abbreviations) == 4
            source_drivers = ("VER", "LEC", "SAI", "RUS")
            abbreviation_map = dict(zip(source_drivers, synthetic_abbreviations))
            fixture["Driver"] = fixture["Driver"].replace(abbreviation_map)
            driver_ids = {
                abbreviation: -88101 - index
                for index, abbreviation in enumerate(synthetic_abbreviations)
            }
            laps = _build_lap_records(
                fixture,
                session_id=-88110,
                driver_ids=driver_ids,
            )
            event_id = -88111
            try:
                connection.execute(
                    text(
                        "INSERT INTO events (event_id, season_year, round_number, "
                        "event_name) VALUES (:id, 2098, 98, 'Fixture Grand Prix')"
                    ),
                    {"id": event_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO sessions (session_id, event_id, session_name, "
                        "session_type) VALUES (-88110, :event_id, 'Race', 'R')"
                    ),
                    {"event_id": event_id},
                )
                for abbreviation, driver_id in driver_ids.items():
                    connection.execute(
                        text(
                            "INSERT INTO drivers (driver_id, abbreviation) "
                            "VALUES (:driver_id, :abbreviation)"
                        ),
                        {"driver_id": driver_id, "abbreviation": abbreviation},
                    )

                records = [
                    record
                    for record in laps
                    if record["lap_time_seconds"] is not None
                ]
                before = connection.execute(
                    text("SELECT count(*) FROM laps WHERE session_id = -88110")
                ).scalar_one()
                assert before == 0
                _insert_many(
                    connection,
                    "laps",
                    LAP_COLUMNS,
                    ("session_id", "driver_id", "lap_number"),
                    records,
                )
                after_first = connection.execute(
                    text("SELECT count(*) FROM laps WHERE session_id = -88110")
                ).scalar_one()
                _insert_many(
                    connection,
                    "laps",
                    LAP_COLUMNS,
                    ("session_id", "driver_id", "lap_number"),
                    records,
                )
                after_second = connection.execute(
                    text("SELECT count(*) FROM laps WHERE session_id = -88110")
                ).scalar_one()
                assert after_first == after_second == len(records) == 19

                clean_count = connection.execute(
                    text(
                        "SELECT count(*) FROM clean_laps "
                        "WHERE year = 2098 AND round = 98"
                    )
                ).scalar_one()
                assert clean_count == 10
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
