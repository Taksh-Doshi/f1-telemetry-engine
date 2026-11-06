"""Tests for tyre-degradation baseline preparation and fitting."""

import numpy as np
import pandas as pd
import pytest

from f1engine.models import (
    cliff_lap,
    evaluate_models_held_out_seasons,
    evaluate_models_leave_one_race_out,
    fit_linear_baselines,
    fit_naive_baseline,
    predict_degradation,
)
from f1engine.tyre_model_v2 import (
    fit_race_fixed_effects_slopes,
    prepare_relative_target,
    save_artifact,
)
from f1engine.tyre_model_v3 import (
    DEFAULT_FUEL_EFFECT_S_PER_KG,
    apply_fuel_correction,
    build_artifact as build_v3_artifact,
    build_fixed_effects_design,
    fit_race_fixed_effects,
    make_synthetic_races,
    prepare_laps,
    synthetic_recovery_experiment,
)


def _synthetic_training_data() -> pd.DataFrame:
    """Make repeated driver laps with a known tyre-age effect and pace offsets."""
    rows = []
    for driver_number in range(6):
        for tyre_age in range(1, 11):
            small_repeatable_noise = (tyre_age % 3 - 1) * 0.01
            rows.append(
                {
                    "circuit": "Example Grand Prix",
                    "compound": "MEDIUM",
                    "driver_code": f"D{driver_number}",
                    "year": 2024,
                    "round": 1,
                    "tyre_life": tyre_age,
                    "lap_number": tyre_age,
                    "fuel_corrected_lap_time_seconds": (
                        80 + driver_number + 0.2 * tyre_age + small_repeatable_noise
                    ),
                }
            )
    return pd.DataFrame(rows)


def test_linear_baseline_estimates_age_slope_with_driver_fixed_effects() -> None:
    training_data = _synthetic_training_data()

    results, fitted_models = fit_linear_baselines(
        training_data,
        min_laps=20,
        min_drivers=5,
    )

    result = results.iloc[0]
    assert result["number_of_laps"] == 60
    assert result["number_of_drivers"] == 6
    assert result["number_of_races"] == 1
    assert result["slope_seconds_per_lap"] == pytest.approx(0.2, abs=0.001)
    assert result["status"] == "Fitted; one race only, descriptive"
    assert ("Example Grand Prix", "MEDIUM") in fitted_models


def test_linear_baseline_reports_small_groups_without_fitting() -> None:
    training_data = _synthetic_training_data()
    training_data = training_data[~training_data["driver_code"].isin(["D4", "D5"])]

    results, fitted_models = fit_linear_baselines(
        training_data,
        min_laps=20,
        min_drivers=5,
    )

    assert results.iloc[0]["status"] == "Too little data"
    assert pd.isna(results.iloc[0]["slope_seconds_per_lap"])
    assert not fitted_models


def test_naive_baseline_is_mean_per_circuit_and_compound() -> None:
    training_data = _synthetic_training_data()

    baseline = fit_naive_baseline(training_data)

    assert len(baseline) == 1
    assert baseline.iloc[0]["number_of_laps"] == 60
    assert baseline.iloc[0]["naive_mean_lap_time_seconds"] == pytest.approx(
        training_data["fuel_corrected_lap_time_seconds"].mean()
    )


def test_baseline_fitting_reports_missing_values_instead_of_dropping_them() -> None:
    training_data = _synthetic_training_data()
    training_data.loc[0, "tyre_life"] = None

    with pytest.raises(ValueError, match="tyre_life=1"):
        fit_linear_baselines(training_data, min_laps=1, min_drivers=1)


def test_leave_one_race_out_evaluates_all_models_without_race_leakage() -> None:
    rows = []
    driver_effects = {f"D{driver}": driver * 0.3 for driver in range(6)}
    for race in range(4):
        for driver in range(6):
            for lap in range(12):
                tyre_age = lap + 1
                compound = ("SOFT", "MEDIUM", "HARD")[lap % 3]
                rows.append(
                    {
                        "year": 2024,
                        "round": race + 1,
                        "circuit": f"Circuit {race}",
                        "driver_code": f"D{driver}",
                        "team": f"Team {driver % 3}",
                        "compound": compound,
                        "tyre_life": tyre_age,
                        "lap_number": lap + 1,
                        "track_temperature_c": 30.0 + race,
                        "fuel_corrected_lap_time_seconds": (
                            70
                            + race
                            + driver_effects[f"D{driver}"]
                            + 0.1 * tyre_age
                            + (0.2 if compound == "SOFT" else 0)
                            + (0.1 if compound == "HARD" else 0)
                            + (lap % 4) * 0.01
                        ),
                    }
                )
    training_data = pd.DataFrame(rows)

    summary, per_race = evaluate_models_leave_one_race_out(
        training_data,
        mixed_max_iterations=50,
        gradient_boosting_iterations=20,
    )

    expected_models = {
        "Naive circuit/compound mean",
        "Pooled driver-fixed-effects linear",
        "Driver random-intercept MixedLM",
        "HistGradientBoostingRegressor",
    }
    assert set(summary["model"]) == expected_models
    assert len(per_race) == 4 * len(expected_models)
    assert summary["number_of_races"].eq(4).all()
    assert summary.loc[
        summary["model"] == "Naive circuit/compound mean",
        "naive_group_fallback_pct",
    ].iloc[0] == pytest.approx(100.0)
    assert summary["mean_race_mae_seconds"].ge(0).all()


def test_leave_one_race_out_requires_multiple_races() -> None:
    training_data = _synthetic_training_data()

    with pytest.raises(ValueError, match="at least two races"):
        evaluate_models_leave_one_race_out(training_data)


def test_held_out_season_evaluation_trains_only_on_earlier_seasons() -> None:
    season_data = []
    for year in (2022, 2023, 2024):
        data = _synthetic_training_data()
        data["year"] = year
        data["circuit"] = f"Circuit {year}"
        season_data.append(data)

    summary, per_season = evaluate_models_held_out_seasons(
        pd.concat(season_data, ignore_index=True),
        mixed_max_iterations=50,
        gradient_boosting_iterations=20,
    )

    assert set(per_season["held_out_year"]) == {2023, 2024}
    assert len(per_season) == 2 * 4
    assert summary["number_of_seasons"].eq(2).all()
    assert summary.loc[
        summary["model"] == "Naive circuit/compound mean",
        "mean_season_mae_seconds",
    ].notna().all()
    assert per_season.loc[
        (per_season["held_out_year"] == 2023)
        & (per_season["model"] == "Naive circuit/compound mean"),
        "naive_group_fallback_pct",
    ].iloc[0] == pytest.approx(100.0)


def _synthetic_race_slopes() -> pd.DataFrame:
    """Make repeated race estimates with known positive and negative wear rates."""
    rows = []
    for race_number, circuit in enumerate(("Circuit A", "Circuit A", "Circuit A")):
        for compound, rank, slope in (
            ("SOFT", "softest", 0.08),
            ("MEDIUM", "middle", 0.05),
            ("HARD", "hardest", 0.03),
        ):
            rows.append(
                {
                    "race_id": f"202{2 + race_number}-1",
                    "year": 2022 + race_number,
                    "round": 1,
                    "circuit": circuit,
                    "compound": compound,
                    "relative_rank": rank,
                    "slope_seconds_per_lap": slope,
                    "standard_error": 0.01,
                    "laps": 60,
                    "drivers": 20,
                    "stints": 20,
                    "status": "fitted",
                    "plausibility_flag": "within_approx_range",
                }
            )
    return pd.DataFrame(rows)


def _synthetic_relative_laps() -> pd.DataFrame:
    """Create staggered stints so tyre age differs within each race lap."""
    rows = []
    wear = {"SOFT": 0.08, "MEDIUM": 0.05, "HARD": 0.03}
    for driver_number in range(12):
        for stint_index, compound in enumerate(("SOFT", "MEDIUM", "HARD")):
            first_race_lap = 1 + (driver_number * 3 + stint_index * 7) % 18
            for stint_lap in range(1, 9):
                race_lap = first_race_lap + stint_lap - 1
                tyre_age = stint_lap + (driver_number % 3)
                rows.append(
                    {
                        "year": 2024,
                        "round": 1,
                        "circuit": "Example Grand Prix",
                        "driver_code": f"D{driver_number}",
                        "team": f"T{driver_number % 4}",
                        "compound": compound,
                        "tyre_life": tyre_age,
                        "stint_number": stint_index + 1,
                        "lap_number": race_lap,
                        "lap_time_seconds": (
                            80
                            + driver_number * 0.3
                            + race_lap * 0.02
                            + wear[compound] * tyre_age
                            + ((stint_lap % 3) - 1) * 0.005
                        ),
                        "fresh_tyre": driver_number % 2 == 0,
                    }
                )
    return pd.DataFrame(rows)


def test_relative_target_counts_exclusions_and_has_no_nan_model_outputs() -> None:
    raw_laps = _synthetic_relative_laps()
    raw_laps.loc[0, "compound"] = None

    relative, audit = prepare_relative_target(raw_laps)

    assert audit["rows_excluded_for_required_fields"] == 1
    assert audit["missing_compound"] == 1
    assert relative["relative_time_seconds"].notna().all()
    assert relative["reference_tyre_age"].notna().all()
    first_three = relative.groupby("driver_stint_id").head(3)
    assert first_three.groupby("driver_stint_id")["relative_time_seconds"].median().abs().max() < 1e-12


def test_per_race_fixed_effects_return_finite_flagged_slopes() -> None:
    relative, _ = prepare_relative_target(_synthetic_relative_laps())

    slopes, status = fit_race_fixed_effects_slopes(
        relative,
        min_compound_laps=20,
        min_drivers=5,
    )

    assert not slopes.empty
    assert slopes["slope_seconds_per_lap"].map(pd.notna).all()
    assert slopes["standard_error"].map(pd.notna).all()
    assert slopes["plausibility_flag"].isin(
        {"within_approx_range", "outside_approx_-0.05_to_0.5"}
    ).all()
    assert status.iloc[0]["status"].startswith(("fitted", "collinear_design"))


def test_per_race_fixed_effects_flag_implausible_slopes() -> None:
    relative, _ = prepare_relative_target(_synthetic_relative_laps())
    soft_rows = relative["compound"].eq("SOFT")
    relative.loc[soft_rows, "relative_time_seconds"] += (
        0.6 * relative.loc[soft_rows, "tyre_life"]
    )

    slopes, _ = fit_race_fixed_effects_slopes(
        relative,
        min_compound_laps=20,
        min_drivers=5,
    )

    soft_slope = slopes.loc[slopes["compound"].eq("SOFT")].iloc[0]
    assert soft_slope["slope_seconds_per_lap"] > 0.5
    assert soft_slope["plausibility_flag"] == "outside_approx_-0.05_to_0.5"


def test_fuel_correction_adds_time_to_return_lap_to_starting_fuel() -> None:
    later_lap = pd.DataFrame(
        [
            {
                "race_laps": 60,
                "lap_number": 2,
                "lap_time_seconds": 90.0,
            }
        ]
    )

    corrected = apply_fuel_correction(
        later_lap,
        fuel_effect_s_per_kg=DEFAULT_FUEL_EFFECT_S_PER_KG,
    )

    assert corrected.loc[0, "fuel_per_lap_kg"] == pytest.approx(110 / 60)
    assert corrected.loc[0, "fuel_corrected_lap_time_seconds"] == pytest.approx(
        90 + (110 / 60 * 0.03)
    )


def test_corrected_race_fixed_effect_design_is_full_rank_on_synthetic_race() -> None:
    raw, _ = make_synthetic_races(race_count=1, driver_count=20)
    laps, _ = prepare_laps(raw)
    race = laps.loc[laps["race_id"].eq(laps["race_id"].iloc[0])]

    corrected_design, _ = build_fixed_effects_design(
        race,
        driver_stint_effect=False,
    )
    flawed_design, _ = build_fixed_effects_design(
        race,
        driver_stint_effect=True,
    )
    _, status = fit_race_fixed_effects(laps)

    assert status.iloc[0]["status"] == "full_rank"
    assert np.linalg.matrix_rank(corrected_design) == corrected_design.shape[1]
    assert np.linalg.matrix_rank(flawed_design) < flawed_design.shape[1]


def test_primary_stint_method_recovers_synthetic_compound_slopes() -> None:
    recovered, _ = synthetic_recovery_experiment()
    primary = recovered.loc[recovered["method"].eq("Primary stint slopes")]

    assert primary["recovered_slope"].notna().all()
    assert (primary["error"].abs() <= 0.03).all()


def _save_test_artifact(tmp_path, slopes: pd.DataFrame | None = None):
    """Write a small complete artifact for isolated API tests."""
    import joblib

    model_path = tmp_path / "relative_model.joblib"
    test_slopes = _synthetic_race_slopes() if slopes is None else slopes
    joblib.dump(
        build_v3_artifact(
            test_slopes,
            max_tyre_age_by_compound={"SOFT": 30, "MEDIUM": 30, "HARD": 30},
        ),
        model_path,
    )
    return model_path


def test_prediction_returns_finite_estimate_interval_and_reliability(
    tmp_path,
) -> None:
    model_path = _save_test_artifact(tmp_path)

    result = predict_degradation(
        "Circuit A",
        "SOFT",
        11,
        model_path=model_path,
    )
    point, lower, upper, reliable = result

    assert len(result) == 4
    assert all(pd.notna(value) for value in (point, lower, upper, reliable))
    assert lower <= point <= upper
    assert point == pytest.approx(0.8)
    assert reliable is True


def test_prediction_warns_and_uses_pooled_estimate_for_sparse_circuit(
    tmp_path,
) -> None:
    model_path = _save_test_artifact(tmp_path)

    with pytest.warns(RuntimeWarning, match="using the cross-circuit pool"):
        point, lower, upper, reliable = predict_degradation(
            "Circuit B",
            "MEDIUM",
            10,
            model_path=model_path,
        )

    assert all(pd.notna(value) for value in (point, lower, upper))
    assert lower <= point <= upper
    assert reliable is False


def test_negative_raw_pool_is_not_silently_clamped(
    tmp_path,
) -> None:
    slopes = _synthetic_race_slopes()
    slopes.loc[slopes["compound"].eq("SOFT"), "slope_seconds_per_lap"] = -0.02
    model_path = _save_test_artifact(tmp_path, slopes)

    point, lower, upper, reliable = predict_degradation(
        "Circuit A",
        "SOFT",
        30,
        model_path=model_path,
    )

    assert point < 0
    assert lower <= point <= upper
    assert lower < 0
    assert reliable is True


def test_cliff_is_a_bounded_planning_threshold(tmp_path) -> None:
    model_path = _save_test_artifact(tmp_path)

    planning_age = cliff_lap(
        "Circuit A",
        "SOFT",
        loss_threshold_seconds=0.5,
        model_path=model_path,
    )

    assert planning_age == 8
    with pytest.raises(ValueError, match="positive and finite"):
        cliff_lap(
            "Circuit A",
            "SOFT",
            loss_threshold_seconds=0,
            model_path=model_path,
        )


def test_prediction_rejects_invalid_tyre_age(tmp_path) -> None:
    model_path = _save_test_artifact(tmp_path)

    with pytest.raises(ValueError, match="at least one lap"):
        predict_degradation("Circuit A", "SOFT", 0, model_path=model_path)


def test_prediction_requires_saved_artifact(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        predict_degradation(
            "Circuit A",
            "SOFT",
            3,
            model_path=tmp_path / "missing.joblib",
        )
