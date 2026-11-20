"""Fuel-robust, race fixed-effects tyre degradation analysis."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

from f1engine.db import PROJECT_ROOT, get_engine
from f1engine.tyre_model_v3 import (
    COMPOUND_ORDER,
    DEFAULT_FUEL_EFFECT_S_PER_KG,
    FUEL_EFFECT_SETTINGS,
    MIN_CIRCUIT_RACES,
    MIN_STINT_LAPS,
    _markdown_table,
    _stint_relative_rows,
    apply_fuel_correction,
    fit_race_fixed_effects,
    fit_stint_slopes,
    load_laps,
    make_synthetic_races,
    pool_stint_slopes,
    prepare_laps,
    synthetic_recovery_experiment,
)


LOGGER = logging.getLogger(__name__)
MODEL_VERSION = 4
MODEL_PATH = PROJECT_ROOT / "models" / "tyre_degradation_v4.joblib"
MIN_RACE_CLEAN_LAPS = 500
FUEL_MISMATCH_SCENARIOS = ((0.04, 0.02), (0.04, 0.03), (0.02, 0.04))


def _random_effect_pool(group: pd.DataFrame) -> dict[str, float | int]:
    """Pool independent race slopes using DerSimonian-Laird random effects."""
    estimates = group["slope_seconds_per_lap"].to_numpy(dtype=float)
    variances = np.square(group["standard_error"].to_numpy(dtype=float))
    valid = np.isfinite(estimates) & np.isfinite(variances) & (variances > 0)
    estimates = estimates[valid]
    variances = variances[valid]
    if not len(estimates):
        raise ValueError("A random-effects pool requires finite race estimates.")

    fixed_weights = 1.0 / variances
    fixed_mean = float(np.sum(fixed_weights * estimates) / np.sum(fixed_weights))
    q_value = float(np.sum(fixed_weights * np.square(estimates - fixed_mean)))
    c_value = float(
        np.sum(fixed_weights) - np.sum(np.square(fixed_weights)) / np.sum(fixed_weights)
    )
    tau_squared = (
        max(0.0, (q_value - (len(estimates) - 1)) / c_value)
        if len(estimates) > 1 and c_value > 0
        else 0.0
    )
    random_weights = 1.0 / (variances + tau_squared)
    pooled = float(np.sum(random_weights * estimates) / np.sum(random_weights))
    standard_error = float(math.sqrt(1.0 / np.sum(random_weights)))
    return {
        "pooled_slope_seconds_per_lap": pooled,
        "lower_95": pooled - 1.96 * standard_error,
        "upper_95": pooled + 1.96 * standard_error,
        "race_estimates": len(estimates),
        "negative_race_slope_share": float(np.mean(estimates < 0)),
        "tau_squared": tau_squared,
    }


def pool_fixed_effects(
    slopes: pd.DataFrame,
    *,
    group_columns: tuple[str, ...] = ("compound",),
    minimum_races: int = 1,
) -> pd.DataFrame:
    """Pool race-level fixed-effect slopes globally or by circuit/compound."""
    if slopes.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for keys, group in slopes.groupby(
        list(group_columns), observed=True, sort=True, dropna=False
    ):
        keys = keys if isinstance(keys, tuple) else (keys,)
        race_count = group["race_id"].nunique()
        if race_count < minimum_races:
            continue
        rows.append(
            {
                **dict(zip(group_columns, keys)),
                **_random_effect_pool(group),
                "laps": int(group["laps"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _race_quality_diagnostics() -> pd.DataFrame:
    """Count raw-lap exclusions for explaining races below the clean-lap rule."""
    statement = text(
        """
        SELECT
            e.season_year AS year,
            e.round_number AS round,
            e.event_name AS circuit,
            count(l.lap_id) AS raw_laps,
            count(*) FILTER (
                WHERE upper(coalesce(l.compound, '')) IN ('INTERMEDIATE', 'WET')
            ) AS wet_compound_laps,
            count(*) FILTER (
                WHERE coalesce(l.track_status, '') ~ '[4567]'
            ) AS safety_or_red_flag_laps,
            count(*) FILTER (
                WHERE l.pit_in_time_seconds IS NOT NULL
                   OR l.pit_out_time_seconds IS NOT NULL
            ) AS pit_laps,
            count(*) FILTER (WHERE l.lap_number = 1) AS opening_laps
        FROM sessions AS s
        JOIN events AS e ON e.event_id = s.event_id
        LEFT JOIN laps AS l ON l.session_id = s.session_id
        WHERE s.session_type = 'R'
        GROUP BY e.season_year, e.round_number, e.event_name
        """
    )
    engine = get_engine()
    try:
        with engine.connect() as connection:
            return pd.read_sql_query(statement, connection)
    finally:
        engine.dispose()


def _quality_status(
    laps: pd.DataFrame,
    fixed_status: pd.DataFrame,
    quality: pd.DataFrame,
) -> pd.DataFrame:
    """Keep every race and mark low-clean-volume or unidentifiable cases."""
    counts = (
        laps.groupby(["race_id"], observed=True)
        .size()
        .rename("clean_laps")
        .reset_index()
    )
    race_rows = quality.copy()
    race_rows["race_id"] = (
        race_rows["year"].astype(str) + "-" + race_rows["round"].astype(str)
    )
    status = race_rows.merge(counts, on="race_id", how="left", validate="one_to_one")
    status["clean_laps"] = status["clean_laps"].fillna(0).astype(int)
    status = status.merge(
        fixed_status.drop(columns=["year", "round", "circuit", "laps"], errors="ignore"),
        on="race_id",
        how="left",
        validate="one_to_one",
    )
    status["status"] = status["status"].fillna("no_clean_laps")
    status["quality_status"] = np.where(
        status["clean_laps"].lt(MIN_RACE_CLEAN_LAPS), "low_data", "eligible"
    )
    status["low_data_reason"] = None
    low_data = status["quality_status"].eq("low_data")
    status.loc[low_data, "low_data_reason"] = status.loc[low_data].apply(
        lambda row: (
            f"{int(row['clean_laps'])} clean laps; minimum is "
            f"{MIN_RACE_CLEAN_LAPS}. Raw lap filters removed/omitted "
            f"{int(row['wet_compound_laps'] if pd.notna(row['wet_compound_laps']) else 0)} wet-compound, "
            f"{int(row['safety_or_red_flag_laps'] if pd.notna(row['safety_or_red_flag_laps']) else 0)} safety/red-flag, "
            f"{int(row['pit_laps'] if pd.notna(row['pit_laps']) else 0)} pit-affected and "
            f"{int(row['opening_laps'] if pd.notna(row['opening_laps']) else 0)} opening laps "
            "(categories may overlap)."
        ),
        axis=1,
    )
    return status


def _eligible_fixed_slopes(
    fixed_slopes: pd.DataFrame, status: pd.DataFrame
) -> pd.DataFrame:
    eligible_races = set(
        status.loc[
            status["quality_status"].eq("eligible")
            & status["status"].eq("full_rank"),
            "race_id",
        ]
    )
    return fixed_slopes.loc[fixed_slopes["race_id"].isin(eligible_races)].copy()


def _synthetic_with_fuel_effect(
    true_fuel_effect_s_per_kg: float,
    *,
    seed: int,
    race_count: int,
    driver_count: int,
    race_laps: int,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Change only the known fuel component in deterministic synthetic races."""
    if not math.isfinite(true_fuel_effect_s_per_kg) or true_fuel_effect_s_per_kg < 0:
        raise ValueError("True fuel effect must be finite and non-negative.")
    laps, truth = make_synthetic_races(
        seed=seed,
        race_count=race_count,
        driver_count=driver_count,
        race_laps=race_laps,
    )
    true_fuel = 110.0 - (110.0 / race_laps) * (laps["lap_number"] - 1)
    laps["lap_time_seconds"] += (
        true_fuel_effect_s_per_kg - DEFAULT_FUEL_EFFECT_S_PER_KG
    ) * true_fuel
    return laps, truth


def fuel_mismatch_experiment(
    *,
    scenarios: tuple[tuple[float, float], ...] = FUEL_MISMATCH_SCENARIOS,
    race_count: int = 9,
    driver_count: int = 18,
    race_laps: int = 60,
) -> pd.DataFrame:
    """Measure wrong-fuel-assumption bias for stint and race-FE estimates."""
    rows: list[dict[str, Any]] = []
    for scenario_index, (true_fuel, assumed_for_stint) in enumerate(scenarios):
        synthetic, truth = _synthetic_with_fuel_effect(
            true_fuel,
            seed=8200 + scenario_index,
            race_count=race_count,
            driver_count=driver_count,
            race_laps=race_laps,
        )
        stint_slopes, _ = fit_stint_slopes(synthetic, assumed_for_stint)
        correctly_adjusted_slopes, _ = fit_stint_slopes(
            synthetic, true_fuel
        )
        for compound in COMPOUND_ORDER:
            compound_stints = stint_slopes.loc[
                stint_slopes["compound"].eq(compound)
            ]
            correct_compound_stints = correctly_adjusted_slopes.loc[
                correctly_adjusted_slopes["compound"].eq(compound)
            ]
            if compound_stints.empty:
                raise RuntimeError(f"No synthetic stint slopes for {compound}.")
            estimate = float(
                np.average(
                    compound_stints["slope_seconds_per_lap"],
                    weights=compound_stints["laps"],
                )
            )
            correct_estimate = float(
                np.average(
                    correct_compound_stints["slope_seconds_per_lap"],
                    weights=correct_compound_stints["laps"],
                )
            )
            rows.append(
                {
                    "true_fuel_effect_s_per_kg": true_fuel,
                    "assumed_fuel_effect_s_per_kg": assumed_for_stint,
                    "method": "Stint slopes",
                    "compound": compound,
                    "true_slope": truth[compound],
                    "estimated_slope": estimate,
                    "bias": estimate - truth[compound],
                    "correct_assumption_slope": correct_estimate,
                    "fuel_mismatch_bias": estimate - correct_estimate,
                    "max_slope_change_across_assumptions": np.nan,
                }
            )

        scenario_fixed: dict[float, pd.DataFrame] = {}
        for assumed_fuel in FUEL_EFFECT_SETTINGS:
            fixed_slopes, status = fit_race_fixed_effects(
                synthetic, assumed_fuel
            )
            full_rank_races = set(
                status.loc[status["status"].eq("full_rank"), "race_id"]
            )
            fixed_slopes = fixed_slopes.loc[
                fixed_slopes["race_id"].isin(full_rank_races)
            ]
            scenario_fixed[assumed_fuel] = fixed_slopes

        for compound in COMPOUND_ORDER:
            estimates_by_assumption: dict[float, float] = {}
            for assumed_fuel, fixed_slopes in scenario_fixed.items():
                compound_slopes = fixed_slopes.loc[
                    fixed_slopes["compound"].eq(compound)
                ]
                if compound_slopes.empty:
                    raise RuntimeError(
                        f"No full-rank synthetic fixed effects for {compound}."
                    )
                estimates_by_assumption[assumed_fuel] = float(
                    compound_slopes["slope_seconds_per_lap"].mean()
                )
            spread = max(estimates_by_assumption.values()) - min(
                estimates_by_assumption.values()
            )
            for assumed_fuel, estimate in estimates_by_assumption.items():
                rows.append(
                    {
                        "true_fuel_effect_s_per_kg": true_fuel,
                        "assumed_fuel_effect_s_per_kg": assumed_fuel,
                        "method": "Race fixed effects",
                        "compound": compound,
                        "true_slope": truth[compound],
                        "estimated_slope": estimate,
                        "bias": estimate - truth[compound],
                        "correct_assumption_slope": np.nan,
                        "fuel_mismatch_bias": np.nan,
                        "max_slope_change_across_assumptions": spread,
                    }
                )
    return pd.DataFrame(rows)


def _artifact_pools(
    global_pools: pd.DataFrame, circuit_pools: pd.DataFrame
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    def as_mapping(frame: pd.DataFrame, key_columns: tuple[str, ...]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for row in frame.to_dict("records"):
            key = "|".join(str(row[column]) for column in key_columns)
            result[key] = {
                "slope": float(row["pooled_slope_seconds_per_lap"]),
                "lower": float(row["lower_95"]),
                "upper": float(row["upper_95"]),
                "races": int(row["race_estimates"]),
            }
        return result

    return as_mapping(global_pools, ("compound",)), as_mapping(
        circuit_pools, ("circuit", "compound")
    )


def build_artifact(
    fixed_slopes: pd.DataFrame,
    status: pd.DataFrame,
    *,
    max_tyre_age_by_compound: dict[str, int],
) -> dict[str, Any]:
    """Build the inference artifact exclusively from eligible full-rank races."""
    eligible_slopes = _eligible_fixed_slopes(fixed_slopes, status)
    global_pools = pool_fixed_effects(eligible_slopes)
    circuit_pools = pool_fixed_effects(
        eligible_slopes,
        group_columns=("circuit", "compound"),
        minimum_races=MIN_CIRCUIT_RACES,
    )
    if global_pools.empty:
        raise RuntimeError("No eligible race fixed-effects pools were produced.")
    global_map, circuit_map = _artifact_pools(global_pools, circuit_pools)
    low_data_races = status.loc[status["quality_status"].eq("low_data")]
    qualifying_races_per_circuit = (
        status.loc[
            status["quality_status"].eq("eligible")
            & status["status"].eq("full_rank")
        ]
        .groupby("circuit", observed=True)["race_id"]
        .nunique()
    )
    circuits_without_enough_races = sorted(
        circuit
        for circuit in status["circuit"].unique()
        if qualifying_races_per_circuit.get(circuit, 0) < MIN_CIRCUIT_RACES
    )
    return {
        "model_version": MODEL_VERSION,
        "model_name": "Race fixed-effects slopes with random-effects pooling",
        "estimator": "Corrected race fixed effects; DerSimonian-Laird pools",
        "fuel_effect_s_per_kg": DEFAULT_FUEL_EFFECT_S_PER_KG,
        "minimum_race_clean_laps": MIN_RACE_CLEAN_LAPS,
        "minimum_circuit_races": MIN_CIRCUIT_RACES,
        "global": global_map,
        "circuits": circuit_map,
        "low_data_races": tuple(low_data_races["race_id"].astype(str)),
        "low_data_circuits": tuple(circuits_without_enough_races),
        "max_tyre_age_by_compound": max_tyre_age_by_compound,
    }


def predict_degradation(
    circuit: str,
    compound: str,
    tyre_life: int,
    *,
    model_path: str | Path = MODEL_PATH,
) -> dict[str, float | bool | str | None]:
    """Return a linear race-FE slope estimate and explicit reliability metadata."""
    if not isinstance(tyre_life, int) or isinstance(tyre_life, bool) or tyre_life < 1:
        raise ValueError("tyre_life must be an integer of at least one lap.")
    if not circuit.strip():
        raise ValueError("circuit cannot be empty.")
    normalised_compound = compound.strip().upper()
    if not normalised_compound:
        raise ValueError("compound cannot be empty.")
    artifact_path = Path(model_path)
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Saved v4 degradation model not found: {artifact_path}")
    artifact = joblib.load(artifact_path)
    if not isinstance(artifact, dict) or artifact.get("model_version") != MODEL_VERSION:
        raise ValueError(f"Unsupported v4 degradation artifact: {artifact_path}")

    circuit_estimate = artifact["circuits"].get(
        f"{circuit}|{normalised_compound}"
    )
    low_data_circuit = circuit in artifact["low_data_circuits"]
    if circuit_estimate is not None and not low_data_circuit:
        estimate = circuit_estimate
        scope = "circuit"
        warning = None
    else:
        estimate = artifact["global"].get(normalised_compound)
        if estimate is None:
            raise ValueError(
                f"No eligible fixed-effects estimate is available for {normalised_compound}."
            )
        scope = "cross-circuit"
        warning = (
            f"{circuit} is flagged low_data or has fewer than "
            f"{MIN_CIRCUIT_RACES} eligible race estimates; using the "
            "cross-circuit pool."
        )

    lower = float(estimate["lower"])
    upper = float(estimate["upper"])
    slope = float(estimate["slope"])
    reliable = lower > 0 or upper < 0
    reliable = reliable and scope == "circuit" and not low_data_circuit
    if not (lower > 0 or upper < 0):
        warning = (
            f"The 95% interval [{lower:.4f}, {upper:.4f}] includes zero; "
            "the slope is not statistically distinguishable from zero."
            if warning is None
            else f"{warning} The 95% interval includes zero."
        )
    return {
        "expected_loss_per_lap": slope,
        "lower_95": lower,
        "upper_95": upper,
        "reliable": bool(reliable),
        "scope": scope,
        "warning": warning,
    }


def cliff_lap(
    circuit: str,
    compound: str,
    *,
    loss_threshold_seconds: float = 1.0,
    model_path: str | Path = MODEL_PATH,
) -> int | None:
    """Return a linear planning threshold, never a detected physical cliff.

    Observed stint end ages are subject to survivorship bias because drivers
    often pit before tyres fall off. A negative slope is retained in the model
    prediction and does not produce a positive-loss planning threshold.
    """
    if not math.isfinite(loss_threshold_seconds) or loss_threshold_seconds <= 0:
        raise ValueError("The planning threshold must be positive and finite.")
    prediction = predict_degradation(
        circuit, compound, 1, model_path=model_path
    )
    slope = float(prediction["expected_loss_per_lap"])
    if slope <= 0:
        return None
    age = int(math.ceil(loss_threshold_seconds / slope)) + 1
    artifact = joblib.load(model_path)
    if age > int(artifact["max_tyre_age_by_compound"].get(compound.upper(), 0)):
        return None
    return age


def _evaluate_fold(
    test_laps: pd.DataFrame,
    train_slopes: pd.DataFrame,
) -> dict[str, float | int]:
    """Compare held-out eligible-stint relative pace with the zero baseline."""
    eligible_stints, _ = fit_stint_slopes(
        test_laps, DEFAULT_FUEL_EFFECT_S_PER_KG, min_laps=MIN_STINT_LAPS
    )
    if eligible_stints.empty:
        return {
            "laps": 0,
            "stints": 0,
            "baseline_relative_mae_seconds": float("nan"),
            "model_relative_mae_seconds": float("nan"),
            "cross_circuit_fallback_stints": 0,
        }

    global_pools = pool_fixed_effects(train_slopes)
    circuit_pools = pool_fixed_effects(
        train_slopes,
        group_columns=("circuit", "compound"),
        minimum_races=MIN_CIRCUIT_RACES,
    )
    global_map, circuit_map = _artifact_pools(global_pools, circuit_pools)
    eval_laps = _stint_relative_rows(
        apply_fuel_correction(test_laps, DEFAULT_FUEL_EFFECT_S_PER_KG)
    )
    eligible_ids = set(eligible_stints["stint_id"])
    eval_laps = eval_laps.loc[eval_laps["stint_id"].isin(eligible_ids)].copy()
    predictions: list[float] = []
    fallback_stints: set[str] = set()
    for row in eval_laps.itertuples(index=False):
        key = f"{row.circuit}|{row.compound}"
        estimate = circuit_map.get(key)
        if estimate is None:
            estimate = global_map.get(str(row.compound))
            fallback_stints.add(str(row.stint_id))
        slope = 0.0 if estimate is None else float(estimate["slope"])
        predictions.append(slope * float(row.relative_tyre_age))
    eval_laps["predicted_relative_time"] = predictions
    return {
        "laps": len(eval_laps),
        "stints": int(eval_laps["stint_id"].nunique()),
        "baseline_relative_mae_seconds": float(
            eval_laps["relative_time_seconds"].abs().mean()
        ),
        "model_relative_mae_seconds": float(
            (
                eval_laps["relative_time_seconds"]
                - eval_laps["predicted_relative_time"]
            )
            .abs()
            .mean()
        ),
        "cross_circuit_fallback_stints": len(fallback_stints),
    }


def evaluate_fixed_effects(
    laps: pd.DataFrame,
    fixed_slopes: pd.DataFrame,
    status: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate race-held-out and chronological predictions, splitting low data."""
    eligible_slopes = _eligible_fixed_slopes(fixed_slopes, status)
    status_by_race = status.set_index("race_id")
    race_rows: list[dict[str, Any]] = []
    for race_id, test_laps in laps.groupby("race_id", sort=True):
        train_slopes = eligible_slopes.loc[eligible_slopes["race_id"].ne(race_id)]
        metrics = _evaluate_fold(test_laps, train_slopes)
        race_status = status_by_race.loc[race_id]
        race_rows.append(
            {
                "race_id": str(race_id),
                "year": int(race_status["year"]),
                "round": int(race_status["round"]),
                "circuit": str(race_status["circuit"]),
                "clean_laps": int(race_status["clean_laps"]),
                "quality_status": str(race_status["quality_status"]),
                **metrics,
            }
        )
    per_race = pd.DataFrame(race_rows)

    def summarize(
        frame: pd.DataFrame, validation: str, data_group: str
    ) -> dict[str, Any]:
        if frame.empty:
            return {
                "validation": validation,
                "data_group": data_group,
                "races": 0,
                "laps": 0,
                "stints": 0,
                "baseline_relative_mae_seconds": float("nan"),
                "model_relative_mae_seconds": float("nan"),
                "cross_circuit_fallback_stints": 0,
            }
        return {
            "validation": validation,
            "data_group": data_group,
            "races": len(frame),
            "laps": int(frame["laps"].sum()),
            "stints": int(frame["stints"].sum()),
            "baseline_relative_mae_seconds": float(
                frame["baseline_relative_mae_seconds"].mean()
            ),
            "model_relative_mae_seconds": float(
                frame["model_relative_mae_seconds"].mean()
            ),
            "cross_circuit_fallback_stints": int(
                frame["cross_circuit_fallback_stints"].sum()
            ),
        }

    summaries: list[dict[str, Any]] = []
    for name, mask in (
        ("eligible", per_race["quality_status"].eq("eligible")),
        ("low_data", per_race["quality_status"].eq("low_data")),
    ):
        summaries.append(
            summarize(per_race.loc[mask], "leave-one-race-out", name)
        )

    test_2024 = per_race.loc[per_race["year"].eq(2024)]
    for name, mask in (
        ("eligible", test_2024["quality_status"].eq("eligible")),
        ("low_data", test_2024["quality_status"].eq("low_data")),
    ):
        summaries.append(
            summarize(
                test_2024.loc[mask],
                "train 2022-2023, test 2024",
                name,
            )
        )
    summary = pd.DataFrame(summaries)
    chronological_rows: list[dict[str, Any]] = []
    train_slopes = eligible_slopes.loc[eligible_slopes["year"].lt(2024)]
    for race_id, test_laps in laps.loc[laps["year"].eq(2024)].groupby(
        "race_id", sort=True
    ):
        metrics = _evaluate_fold(test_laps, train_slopes)
        race_status = status_by_race.loc[race_id]
        chronological_rows.append(
            {
                "race_id": str(race_id),
                "year": 2024,
                "round": int(race_status["round"]),
                "circuit": str(race_status["circuit"]),
                "clean_laps": int(race_status["clean_laps"]),
                "quality_status": str(race_status["quality_status"]),
                **metrics,
            }
        )
    chronological = pd.DataFrame(chronological_rows)
    return summary, per_race, chronological


def _fuel_sensitivity_table(
    slopes_by_fuel: dict[float, pd.DataFrame],
    status_by_fuel: dict[float, pd.DataFrame],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fuel_effect in FUEL_EFFECT_SETTINGS:
        status = status_by_fuel[fuel_effect]
        slopes = _eligible_fixed_slopes(
            slopes_by_fuel[fuel_effect], status
        )
        pools = pool_fixed_effects(slopes)
        for row in pools.to_dict("records"):
            rows.append(
                {
                    "assumed_fuel_effect_s_per_kg": fuel_effect,
                    **row,
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    default = table.loc[
        table["assumed_fuel_effect_s_per_kg"].eq(DEFAULT_FUEL_EFFECT_S_PER_KG)
    ].set_index("compound")["pooled_slope_seconds_per_lap"]
    table["difference_from_0.03"] = table.apply(
        lambda row: row["pooled_slope_seconds_per_lap"]
        - default.loc[row["compound"]],
        axis=1,
    )
    return table


def run_analysis() -> dict[str, Any]:
    """Fit v4, compare fuel assumptions, validate and write current reports."""
    raw_laps = load_laps()
    laps, exclusions = prepare_laps(raw_laps)
    if laps.empty:
        raise RuntimeError("No complete clean laps are available for model fitting.")
    quality = _race_quality_diagnostics()

    slopes_by_fuel: dict[float, pd.DataFrame] = {}
    status_by_fuel: dict[float, pd.DataFrame] = {}
    stint_sensitivity: list[pd.DataFrame] = []
    for fuel_effect in FUEL_EFFECT_SETTINGS:
        fixed_slopes, fixed_status = fit_race_fixed_effects(laps, fuel_effect)
        status = _quality_status(laps, fixed_status, quality)
        slopes_by_fuel[fuel_effect] = fixed_slopes
        status_by_fuel[fuel_effect] = status

        stint_slopes, _ = fit_stint_slopes(laps, fuel_effect)
        global_pool, _ = pool_stint_slopes(
            stint_slopes,
            seed=20261106 + FUEL_EFFECT_SETTINGS.index(fuel_effect) * 1000,
        )
        global_pool.insert(0, "assumed_fuel_effect_s_per_kg", fuel_effect)
        stint_sensitivity.append(global_pool)

    default_slopes = slopes_by_fuel[DEFAULT_FUEL_EFFECT_S_PER_KG]
    default_status = status_by_fuel[DEFAULT_FUEL_EFFECT_S_PER_KG]
    eligible_slopes = _eligible_fixed_slopes(default_slopes, default_status)
    global_pools = pool_fixed_effects(eligible_slopes)
    circuit_pools = pool_fixed_effects(
        eligible_slopes,
        group_columns=("circuit", "compound"),
        minimum_races=MIN_CIRCUIT_RACES,
    )
    fuel_sensitivity = _fuel_sensitivity_table(
        slopes_by_fuel, status_by_fuel
    )
    mismatch = fuel_mismatch_experiment()
    recovery, recovery_details = synthetic_recovery_experiment()
    validation, per_race_validation, chronological = evaluate_fixed_effects(
        laps, default_slopes, default_status
    )

    max_age = (
        laps.groupby("compound", observed=True)["tyre_life"]
        .max()
        .astype(int)
        .to_dict()
    )
    artifact = build_artifact(
        default_slopes,
        default_status,
        max_tyre_age_by_compound={str(key): int(value) for key, value in max_age.items()},
    )
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH, compress=3)

    full_rank = default_status["status"].eq("full_rank")
    summary = {
        "source_rows": int(len(raw_laps)),
        "usable_rows": int(len(laps)),
        "races": int(laps["race_id"].nunique()),
        "low_data_races": int(default_status["quality_status"].eq("low_data").sum()),
        "full_rank_races": int(full_rank.sum()),
        "rank_deficient_races": int(default_status["status"].eq("rank_deficient").sum()),
        "failed_races": int(default_status["status"].astype(str).str.startswith("failed:").sum()),
        "eligible_fixed_effect_races": int(
            default_status["quality_status"].eq("eligible")
            .mul(full_rank)
            .sum()
        ),
        "minimum_race_clean_laps": MIN_RACE_CLEAN_LAPS,
        "eligible_race_fixed_effects": len(eligible_slopes),
    }
    report = _make_report(
        summary=summary,
        exclusions=exclusions,
        default_status=default_status,
        global_pools=global_pools,
        circuit_pools=circuit_pools,
        fuel_sensitivity=fuel_sensitivity,
        stint_sensitivity=pd.concat(stint_sensitivity, ignore_index=True),
        mismatch=mismatch,
        recovery=recovery,
        validation=validation,
        per_race_validation=per_race_validation,
        chronological=chronological,
        artifact_path=MODEL_PATH,
    )
    (PROJECT_ROOT / "docs" / "results_v4.md").write_text(report, encoding="utf-8")
    (PROJECT_ROOT / "docs" / "model_results.md").write_text(report, encoding="utf-8")
    return {
        "raw_laps": raw_laps,
        "laps": laps,
        "exclusions": exclusions,
        "fixed_slopes_by_fuel": slopes_by_fuel,
        "fixed_status_by_fuel": status_by_fuel,
        "fixed_slopes": default_slopes,
        "fixed_status": default_status,
        "global_pools": global_pools,
        "circuit_pools": circuit_pools,
        "fuel_sensitivity": fuel_sensitivity,
        "stint_sensitivity": pd.concat(stint_sensitivity, ignore_index=True),
        "fuel_mismatch": mismatch,
        "synthetic_recovery": recovery,
        "synthetic_details": recovery_details,
        "validation": validation,
        "per_race_validation": per_race_validation,
        "chronological_validation": chronological,
        "summary": summary,
        "artifact_path": MODEL_PATH,
    }


def _make_report(
    *,
    summary: dict[str, Any],
    exclusions: dict[str, Any],
    default_status: pd.DataFrame,
    global_pools: pd.DataFrame,
    circuit_pools: pd.DataFrame,
    fuel_sensitivity: pd.DataFrame,
    stint_sensitivity: pd.DataFrame,
    mismatch: pd.DataFrame,
    recovery: pd.DataFrame,
    validation: pd.DataFrame,
    per_race_validation: pd.DataFrame,
    chronological: pd.DataFrame,
    artifact_path: Path,
) -> str:
    low_data = default_status.loc[
        default_status["quality_status"].eq("low_data"),
        ["race_id", "circuit", "clean_laps", "low_data_reason"],
    ]
    rank_deficient = default_status.loc[
        default_status["status"].eq("rank_deficient"),
        ["race_id", "circuit", "clean_laps", "design_rank", "design_columns"],
    ]
    fuel_spread = (
        fuel_sensitivity.groupby("compound", observed=True)["pooled_slope_seconds_per_lap"]
        .agg(lambda values: float(values.max() - values.min()))
        .rename("max_abs_slope_change")
        .reset_index()
    )
    return f"""# Tyre degradation v4: race fixed-effects headline

## Headline method and eligibility

V4 uses the corrected race fixed-effects estimator as its headline. Each race
fit controls for driver, race lap, and compound intercepts, then estimates a
separate tyre-age slope by compound. Only full-column-rank designs contribute
to the reported race estimates. Independent race-level slopes are pooled with
DerSimonian-Laird random effects and normal 95% intervals.

The minimum data rule is {MIN_RACE_CLEAN_LAPS} clean race laps in the existing
`clean_laps` view and at least {MIN_CIRCUIT_RACES} full-rank races for a
circuit/compound pool. Below-threshold races remain in the status and
per-race tables but are excluded from circuit pools and headline validation.
Circuit/compound groups without three qualifying races use the cross-circuit
pool and are marked as such in the prediction API. Clean-lap totals can be
reduced by the view's pit, safety/red flag, wet compound, inaccurate/deleted,
and lap-one filters.

## Data accounting

- Source rows: {summary['source_rows']:,}; complete model rows: {summary['usable_rows']:,}.
- Excluded rows with missing/invalid required values: {exclusions['rows_excluded_missing_or_invalid_required_fields']:,}.
- Race sessions with clean data: {summary['races']}; eligible full-rank races: {summary['eligible_fixed_effect_races']}; rank-deficient: {summary['rank_deficient_races']}; failed fits: {summary['failed_races']}.

### Low-data races

{_markdown_table(low_data)}

### Rank-deficient race designs

{_markdown_table(rank_deficient)}

## Headline race fixed-effects degradation

Slopes are seconds per tyre-age lap; negative estimates are retained, not
clamped. Circuit pools include only eligible full-rank races and require at
least {MIN_CIRCUIT_RACES} distinct race estimates.

### Cross-circuit pools

{_markdown_table(global_pools)}

### Circuit/compound pools

{_markdown_table(circuit_pools)}

## Fuel mismatch and fuel-assumption sensitivity

Race-lap fixed effects absorb the shared lap-by-lap fuel trend. Synthetic
experiments compare a known true fuel effect with a mismatched correction.
Within-stint slopes move with the difference in fuel assumptions; the race
fixed-effects slopes should remain invariant across assumed fuel settings.

{_markdown_table(mismatch)}

Maximum spread in cross-circuit fixed-effects estimates across the 0.02, 0.03,
and 0.04 s/kg assumptions:

{_markdown_table(fuel_spread)}

The within-stint estimates are shown only as a labelled sensitivity check:

{_markdown_table(stint_sensitivity)}

## Synthetic parameter recovery

{_markdown_table(recovery)}

Fuel mismatch is reported separately above; recovery is not evidence that
real-world confounding has been eliminated.

## Held-out evaluation

Relative lap-time MAE compares the headline fixed-effects pools with a
zero-degradation baseline. Eligible and low-data races are summarized
separately. Leave-one-race-out excludes the held-out race from the training
pools. The chronological evaluation trains on 2022-2023 and tests on 2024.

### Summary; only eligible rows are the headline

{_markdown_table(validation)}

### 2024 chronological races

{_markdown_table(chronological)}

### Per-race leave-one-out results, including low-data rows

{_markdown_table(per_race_validation)}

## Limitations

The model modestly beats the zero-degradation baseline in the eligible
held-out summaries above, but this is not causal validation. Race fixed
effects remove shared lap evolution, while race exclusions and rank deficiency
limit coverage. Fuel correction is approximate; the fixed-effects estimator
is invariant to this particular linear fuel term because race-lap effects
absorb it. Weekend-relative SOFT/MEDIUM/HARD labels do not identify the
underlying Pirelli C1-C5 rubber, and pooled estimates may not distinguish
compounds. Circuit intervals can be wide, especially with few qualifying
races. Drivers often pit before tyre fall-off, creating survivorship bias.
Do not treat estimates or `cliff_lap` outputs as detected physical cliffs or
pit-strategy advice.

The v4 artifact is `{artifact_path.relative_to(PROJECT_ROOT)}`. The earlier
stint-slope analysis remains documented in [results_v3.md](results_v3.md).
"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = run_analysis()
    print("Tyre degradation v4 analysis complete.")
    print(pd.DataFrame([results["summary"]]).to_string(index=False))
    print("\nHeadline race fixed-effects pools:")
    print(results["global_pools"].to_string(index=False))
    print(f"\nArtifact: {results['artifact_path']}")
    print("Reports: docs/results_v4.md and docs/model_results.md")


if __name__ == "__main__":
    main()
