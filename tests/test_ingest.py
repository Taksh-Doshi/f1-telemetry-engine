import logging
from unittest.mock import Mock, call

import pandas as pd

from f1engine import ingest
from f1engine.ingest import (
    _build_lap_records,
    _build_lap_telemetry_summary,
    _build_stint_records,
    _persist_lap_summaries,
    _build_telemetry_sample_records,
)


def test_lap_records_preserve_raw_laps_and_convert_values(caplog):
    laps = pd.DataFrame(
        {
            "Driver": ["VER", "VER", "VER"],
            "LapNumber": [1.0, 2.0, 3.0],
            "LapTime": [
                pd.Timedelta(seconds=90.25),
                pd.NaT,
                pd.Timedelta(seconds=91.5),
            ],
            "Sector1Time": [pd.Timedelta(seconds=30.0), pd.NaT, pd.NaT],
            "Sector2Time": [pd.NaT, pd.NaT, pd.NaT],
            "Sector3Time": [pd.NaT, pd.NaT, pd.NaT],
            "SpeedI1": [300.0, float("nan"), 305.0],
            "Compound": ["soft", "NOT_A_COMPOUND", None],
            "TyreLife": [1.0, 2.0, 3.0],
            "FreshTyre": [True, False, None],
            "Stint": [1.0, 1.0, 1.0],
            "TrackStatus": ["1", "4", "1"],
            "Deleted": [False, True, False],
            "PitInTime": [pd.NaT, pd.Timedelta(seconds=190.25), pd.NaT],
            "PitOutTime": [pd.Timedelta(seconds=0.5), pd.NaT, pd.NaT],
            "Team": ["Red Bull Racing", "Red Bull Racing", "Red Bull Racing"],
        }
    )

    with caplog.at_level(logging.WARNING):
        records = _build_lap_records(laps, session_id=7, driver_ids={"VER": 4})

    assert len(records) == 3
    assert records[0]["lap_time_seconds"] == 90.25
    assert records[0]["sector1_seconds"] == 30.0
    assert records[0]["speed_i1"] == 300.0
    assert records[0]["compound"] == "SOFT"
    assert records[0]["pit_out_time_seconds"] == 0.5
    assert records[1]["lap_time_seconds"] is None
    assert records[1]["speed_i1"] is None
    assert records[1]["pit_in_time_seconds"] == 190.25
    assert records[1]["track_status"] == "4"
    assert records[1]["deleted"] is True
    assert records[1]["compound"] is None
    assert records[2]["compound"] is None
    assert records[0]["team"] == "Red Bull Racing"
    assert "Unknown tyre compound" in caplog.text


def test_stint_records_use_first_and_last_lap():
    laps = [
        {
            "session_id": 7,
            "driver_id": 4,
            "lap_number": 2,
            "stint_number": 1,
            "compound": "MEDIUM",
            "tyre_life": 2,
            "fresh_tyre": False,
        },
        {
            "session_id": 7,
            "driver_id": 4,
            "lap_number": 1,
            "stint_number": 1,
            "compound": "MEDIUM",
            "tyre_life": 1,
            "fresh_tyre": True,
        },
        {
            "session_id": 7,
            "driver_id": 4,
            "lap_number": 3,
            "stint_number": None,
            "compound": None,
            "tyre_life": None,
            "fresh_tyre": None,
        },
    ]

    assert _build_stint_records(laps) == [
        {
            "session_id": 7,
            "driver_id": 4,
            "stint_number": 1,
            "start_lap": 1,
            "end_lap": 2,
            "compound": "MEDIUM",
            "tyre_age_at_start": 1,
            "fresh_tyre": True,
        }
    ]


def test_lap_telemetry_summary_uses_only_samples_inside_the_lap():
    telemetry = pd.DataFrame(
        {
            "SessionTime": pd.to_timedelta([0, 1, 2, 3], unit="s"),
            "Speed": [100, 200, 300, 400],
            "Throttle": [0, 95, 100, 0],
            "Brake": [False, False, True, False],
            "DRS": [0, 0, 10, 0],
            "nGear": [1, 2, 3, 4],
        }
    )

    summary = _build_lap_telemetry_summary(
        telemetry,
        pd.Timedelta(seconds=1),
        pd.Timedelta(seconds=2),
    )

    assert summary == {
        "top_speed": 300.0,
        "mean_speed": 250.0,
        "mean_throttle": 97.5,
        "full_throttle_pct": 50.0,
        "brake_pct": 50.0,
        "drs_pct": 50.0,
        "gear_changes": 1.0,
    }


def test_persist_lap_summaries_builds_one_record_for_the_lap(monkeypatch):
    connection = Mock()
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {"lap_id": 45, "lap_number": 1, "abbreviation": "VER"}
    ]
    session = Mock()
    session.laps = pd.DataFrame(
        {
            "Driver": ["VER"],
            "LapNumber": [1],
            "LapStartTime": [pd.Timedelta(seconds=1)],
            "LapTime": [pd.Timedelta(seconds=2)],
        }
    )
    session.car_data = {
        "1": pd.DataFrame(
            {
                "SessionTime": pd.to_timedelta([1, 2], unit="s"),
                "Speed": [200, 300],
                "Throttle": [95, 100],
                "Brake": [False, True],
                "DRS": [0, 10],
                "nGear": [2, 3],
            }
        )
    }
    session.get_driver.return_value = Mock(Abbreviation="VER")
    insert = Mock()
    monkeypatch.setattr(ingest, "_insert_many", insert)

    count = _persist_lap_summaries(connection, session, session_id=7)

    assert count == 1
    insert.assert_called_once()
    assert insert.call_args.args[1] == "lap_telemetry_summary"
    assert insert.call_args.args[4] == [
        {
            "lap_id": 45,
            "top_speed": 300.0,
            "mean_speed": 250.0,
            "mean_throttle": 97.5,
            "full_throttle_pct": 50.0,
            "brake_pct": 50.0,
            "drs_pct": 50.0,
            "gear_changes": 1.0,
        }
    ]


def test_telemetry_sample_records_align_channels_and_assign_laps():
    car_data = pd.DataFrame(
        {
            "SessionTime": pd.to_timedelta([0.1, 0.5, 1.0, 2.0], unit="s"),
            "Speed": [100, 150, 200, 250],
            "Throttle": [20, 50, 80, 100],
            "Brake": [False, True, False, False],
            "nGear": [2, 3, 4, 5],
            "RPM": [8000, 9000, 10000, 11000],
            "DRS": [0, 1, 10, 12],
        }
    )
    position_data = pd.DataFrame(
        {
            "SessionTime": pd.to_timedelta([0.12, 0.52, 1.02, 2.02], unit="s"),
            "X": [10, 20, 30, 40],
            "Y": [1, 2, 3, 4],
        }
    )
    lap_data = pd.DataFrame(
        {
            "LapNumber": [1, 2],
            "LapStartTime": pd.to_timedelta([0, 1], unit="s"),
        }
    )

    records = _build_telemetry_sample_records(
        car_data,
        position_data,
        lap_data,
        session_id=9,
        driver_id=4,
        stored_lap_numbers={1, 2},
    )

    assert len(records) == 4
    assert records[0] == {
        "session_id": 9,
        "driver_id": 4,
        "lap_number": 1,
        "time_seconds": 0.1,
        "speed": 100.0,
        "throttle": 20.0,
        "brake": False,
        "gear": 2,
        "rpm": 8000,
        "drs": 0,
        "x": 10.0,
        "y": 1.0,
    }
    assert [record["lap_number"] for record in records] == [1, 1, 2, 2]
    assert records[2]["x"] == 30.0


def test_ingest_session_loads_telemetry_for_summary_creation(monkeypatch):
    f1_session = Mock(name="mock session")
    f1_session.name = "Race"
    engine = Mock()
    monkeypatch.setattr(ingest, "_cache_directory", Mock())
    monkeypatch.setattr(ingest.fastf1, "get_session", Mock(return_value=f1_session))
    monkeypatch.setattr(ingest, "get_engine", Mock(return_value=engine))
    monkeypatch.setattr(ingest, "run_schema", Mock())
    persist = Mock(return_value=10)
    monkeypatch.setattr(ingest, "_persist_session", persist)

    assert ingest.ingest_session(2024, 1) == 10

    f1_session.load.assert_called_once_with(
        telemetry=True,
        messages=False,
        weather=True,
    )
    persist.assert_called_once()
    engine.dispose.assert_called_once_with()


def test_ingest_season_skips_stored_races_and_continues_after_failure(
    monkeypatch, caplog
):
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2, 3, 4],
            "EventName": ["Race One", "Race Two", "Race Three", "Race Four"],
        }
    )
    schedule_loader = Mock(return_value=schedule)
    engine = Mock()
    schema_runner = Mock()
    ingest_counts = {1: (100, 100), 2: (0, 0), 3: (0, 0), 4: (100, 25)}

    def count_stored_data(count_engine, year, round_number, session_type):
        assert count_engine is engine
        assert year == 2024
        assert session_type == "R"
        return ingest_counts[round_number]

    stored_counts = Mock(side_effect=count_stored_data)

    def ingest_round(year, round_number, session_type):
        assert year == 2024
        assert session_type == "R"
        if round_number == 2:
            raise RuntimeError("test failure")
        return 150

    monkeypatch.setattr(ingest, "_cache_directory", Mock())
    monkeypatch.setattr(ingest.fastf1, "get_event_schedule", schedule_loader)
    monkeypatch.setattr(ingest, "get_engine", Mock(return_value=engine))
    monkeypatch.setattr(ingest, "run_schema", schema_runner)
    monkeypatch.setattr(ingest, "_stored_ingest_counts", stored_counts)
    monkeypatch.setattr(ingest, "ingest_session", ingest_round)
    sleep = Mock()
    monkeypatch.setattr(ingest.time, "sleep", sleep)

    with caplog.at_level(logging.ERROR):
        summary = ingest.ingest_season(2024)

    schedule_loader.assert_called_once_with(2024, include_testing=False)
    schema_runner.assert_called_once_with(engine)
    assert stored_counts.call_args_list == [
        call(engine, 2024, 1, "R"),
        call(engine, 2024, 2, "R"),
        call(engine, 2024, 3, "R"),
        call(engine, 2024, 4, "R"),
    ]
    assert summary["rounds_succeeded"] == 3
    assert summary["rounds_failed"] == 1
    assert summary["successful_round_numbers"] == [1, 3, 4]
    assert summary["failed_rounds"][0]["round"] == 2
    assert summary["total_laps"] == 400
    assert "continuing with the next race" in caplog.text
    assert sleep.call_args_list == [call(2), call(2), call(2)]
    engine.dispose.assert_called_once_with()
