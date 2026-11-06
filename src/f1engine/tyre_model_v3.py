"""Stint-slope tyre degradation analysis with race-clustered uncertainty."""

from __future__ import annotations

import logging
import math
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from f1engine.db import PROJECT_ROOT
from f1engine.tyre_model_v2 import load_relative_training_data

LOGGER = logging.getLogger(__name__)
MODEL_VERSION = 3
MODEL_PATH = PROJECT_ROOT / "models" / "tyre_degradation_v3.joblib"
FUEL_EFFECT_SETTINGS = (0.02, 0.03, 0.04)
DEFAULT_FUEL_EFFECT_S_PER_KG = 0.03
MIN_STINT_LAPS = 8
MIN_CIRCUIT_RACES = 3
BOOTSTRAP_REPLICATES = 1000
COMPOUND_ORDER = ("SOFT", "MEDIUM", "HARD")
KNOWN_COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")

REQUIRED_COLUMNS = (
    "year",
    "round",
    "circuit",
    "driver_code",
    "compound",
    "tyre_life",
    "stint_number",
    "lap_number",
    "lap_time_seconds",
)


def load_laps() -> pd.DataFrame:
    """Load the clean race-lap view without printing connection settings."""
    return load_relative_training_data()


def prepare_laps(raw_laps: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate model fields and count every row/stint excluded from fitting."""
    missing_columns = set(REQUIRED_COLUMNS).difference(raw_laps.columns)
    if missing_columns:
        raise ValueError(
            "Lap data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    data = raw_laps.copy()
    numeric_columns = ("year", "round", "tyre_life", "stint_number", "lap_number", "lap_time_seconds")
    invalid_numeric = pd.DataFrame(index=data.index)
    for column in numeric_columns:
        original = data[column].copy()
        data[column] = pd.to_numeric(data[column], errors="coerce")
        values = data[column].to_numpy(dtype=float)
        invalid_numeric[column] = original.notna() & (
            data[column].isna() | ~np.isfinite(values)
        )

    missing_by_field = {column: int(data[column].isna().sum()) for column in REQUIRED_COLUMNS}
    bad_numeric_by_field = {
        column: int(invalid_numeric[column].sum()) for column in numeric_columns
    }

    # Race length is computed before model-row exclusions, using every numeric
    # race lap in the source, so a missing tyre field cannot shorten the race.
    race_keys = ["year", "round"]
    race_lengths = (
        data.dropna(subset=[*race_keys, "lap_number"])
        .groupby(race_keys, observed=True)["lap_number"]
        .max()
        .rename("race_laps")
    )
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["round"] = pd.to_numeric(data["round"], errors="coerce")
    # Recompute the maximum from source lap rows instead of trusting a stale
    # precomputed race_laps column that may have come with a fixture.
    data = data.drop(columns=["race_laps"], errors="ignore")
    data = data.join(race_lengths, on=race_keys)

    invalid_rows = data[list(REQUIRED_COLUMNS)].isna().any(axis=1)
    invalid_rows |= invalid_numeric.any(axis=1)
    invalid_rows |= data["race_laps"].isna() | data["race_laps"].le(0)
    exclusions: dict[str, Any] = {
        "input_rows": len(data),
        "rows_excluded_missing_or_invalid_required_fields": int(invalid_rows.sum()),
        "missing_values_by_field": missing_by_field,
        "invalid_numeric_by_field": bad_numeric_by_field,
        "source_rows_with_unknown_compounds": int(
            (
                data["compound"].notna()
                & ~data["compound"].astype(str).str.upper().isin(KNOWN_COMPOUNDS)
            ).sum()
        ),
        "stints_shorter_than_minimum": 0,
        "stints_with_multiple_compounds": 0,
        "stints_without_tyre_age_variation": 0,
        "laps_removed_by_optional_slow_lap_filter": 0,
    }

    # The requested 3% slow-lap filter is optional. We deliberately keep all
    # rows in clean_laps rather than make a subjective traffic/error exclusion.
    data = data.loc[~invalid_rows].copy()
    data["year"] = data["year"].astype(int)
    data["round"] = data["round"].astype(int)
    data["stint_number"] = data["stint_number"].astype(int)
    data["lap_number"] = data["lap_number"].astype(int)
    data["compound"] = data["compound"].astype(str).str.upper()
    data["race_id"] = data["year"].astype(str) + "-" + data["round"].astype(str)
    data["stint_id"] = (
        data["race_id"]
        + "|"
        + data["driver_code"].astype(str)
        + "|"
        + data["stint_number"].astype(str)
    )
    data["stint_lap_number"] = data.groupby("stint_id", sort=False).cumcount() + 1

    compound_counts = data.groupby("stint_id", sort=False)["compound"].nunique()
    mixed_stints = set(compound_counts[compound_counts.gt(1)].index)
    exclusions["stints_with_multiple_compounds"] = len(mixed_stints)
    if mixed_stints:
        LOGGER.warning(
            "%s stints have multiple compound labels and will not be fitted as one stint.",
            len(mixed_stints),
        )
    data["mixed_compound_stint"] = data["stint_id"].isin(mixed_stints)
    data = data.sort_values(
        ["year", "round", "driver_code", "stint_number", "lap_number"]
    ).reset_index(drop=True)
    return data, exclusions


def apply_fuel_correction(
    laps: pd.DataFrame,
    fuel_effect_s_per_kg: float = DEFAULT_FUEL_EFFECT_S_PER_KG,
) -> pd.DataFrame:
    """Add the estimated fuel-weight time penalty back to each later lap.

    Approximate assumptions: each race starts with 110 kg of fuel, and
    ``fuel_effect_s_per_kg`` is an assumed lap-time effect, not a measured
    value. Less fuel makes a later lap faster. To express that lap at the
    starting fuel load, ADD the time penalty for the fuel already burned:
    ``corrected = observed + (110 / race_laps) * effect * (lap - 1)``.
    Subtracting this positive penalty would make the corrected lap faster,
    which is the opposite of the stated starting-fuel convention.
    """
    if not math.isfinite(fuel_effect_s_per_kg) or fuel_effect_s_per_kg < 0:
        raise ValueError("Fuel effect must be finite and non-negative.")
    corrected = laps.copy()
    corrected["fuel_per_lap_kg"] = 110.0 / corrected["race_laps"]
    corrected["fuel_correction_per_lap_seconds"] = (
        corrected["fuel_per_lap_kg"] * fuel_effect_s_per_kg
    )
    correction = corrected["fuel_correction_per_lap_seconds"] * (
        corrected["lap_number"] - 1
    )
    corrected["fuel_corrected_lap_time_seconds"] = (
        corrected["lap_time_seconds"] + correction
    )
    corrected["fuel_effect_s_per_kg"] = fuel_effect_s_per_kg
    return corrected


def fit_stint_slopes(
    laps: pd.DataFrame,
    fuel_effect_s_per_kg: float = DEFAULT_FUEL_EFFECT_S_PER_KG,
    *,
    min_laps: int = MIN_STINT_LAPS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fit OLS lap-time-on-tyre-age slopes, retaining all qualifying laps."""
    if min_laps < 3:
        raise ValueError("At least three laps are required to estimate a slope.")
    corrected = apply_fuel_correction(laps, fuel_effect_s_per_kg)
    rows: list[dict[str, Any]] = []
    short_stints = 0
    no_age_variation = 0
    mixed_stints = 0

    for stint_id, stint in corrected.groupby("stint_id", sort=True):
        if stint["mixed_compound_stint"].any():
            mixed_stints += 1
            continue
        if len(stint) < min_laps:
            short_stints += 1
            continue
        age = stint["tyre_life"].to_numpy(dtype=float)
        time = stint["fuel_corrected_lap_time_seconds"].to_numpy(dtype=float)
        centered_age = age - age.mean()
        sum_squares = float(np.dot(centered_age, centered_age))
        if sum_squares <= 0:
            no_age_variation += 1
            continue
        slope = float(np.dot(centered_age, time - time.mean()) / sum_squares)
        intercept = float(time.mean() - slope * age.mean())
        residuals = time - (intercept + slope * age)
        degrees_freedom = len(stint) - 2
        variance = float(np.dot(residuals, residuals) / degrees_freedom)
        standard_error = float(math.sqrt(max(0.0, variance / sum_squares)))
        first_three = stint.sort_values("lap_number").head(3)
        rows.append(
            {
                "race_id": str(stint["race_id"].iloc[0]),
                "year": int(stint["year"].iloc[0]),
                "round": int(stint["round"].iloc[0]),
                "circuit": str(stint["circuit"].iloc[0]),
                "driver_code": str(stint["driver_code"].iloc[0]),
                "stint_number": int(stint["stint_number"].iloc[0]),
                "stint_id": str(stint_id),
                "compound": str(stint["compound"].iloc[0]),
                "slope_seconds_per_lap": slope,
                "standard_error": standard_error,
                "laps": len(stint),
                "reference_tyre_age": float(first_three["tyre_life"].median()),
                "minimum_tyre_age": float(age.min()),
                "maximum_tyre_age": float(age.max()),
            }
        )

    audit = {
        "stints_fitted": len(rows),
        "stints_shorter_than_minimum_for_this_setting": short_stints,
        "stints_without_tyre_age_variation": no_age_variation,
        "multiple_compound_stints_skipped_in_this_fit": mixed_stints,
        "laps_removed_by_optional_slow_lap_filter": 0,
    }
    return pd.DataFrame(rows), audit


def _weighted_mean(slopes: pd.DataFrame) -> float:
    """Use stint length as the pool weight to avoid unstable inverse variances."""
    values = slopes["slope_seconds_per_lap"].to_numpy(dtype=float)
    weights = slopes["laps"].to_numpy(dtype=float)
    return float(np.average(values, weights=weights))


def cluster_bootstrap_interval(
    slopes: pd.DataFrame,
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = 20261106,
) -> tuple[float, float, int]:
    """Bootstrap whole races, keeping all stints from a sampled race together."""
    if replicates < 100:
        raise ValueError("Use at least 100 cluster-bootstrap replicates.")
    races = np.asarray(sorted(slopes["race_id"].astype(str).unique()))
    if not len(races):
        return float("nan"), float("nan"), 0
    by_race = {
        race: slopes.loc[slopes["race_id"].astype(str).eq(race)]
        for race in races
    }
    generator = np.random.default_rng(seed)
    bootstrap_means: list[float] = []
    for _ in range(replicates):
        sampled_races = generator.choice(races, size=len(races), replace=True)
        sampled = pd.concat([by_race[race] for race in sampled_races], ignore_index=True)
        if not sampled.empty:
            bootstrap_means.append(_weighted_mean(sampled))
    if not bootstrap_means:
        return float("nan"), float("nan"), 0
    lower, upper = np.quantile(bootstrap_means, [0.025, 0.975])
    return float(lower), float(upper), len(bootstrap_means)


def pool_stint_slopes(
    slopes: pd.DataFrame,
    *,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = 20261106,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pool slopes by compound and by circuit when at least three races exist."""
    if slopes.empty:
        return pd.DataFrame(), pd.DataFrame()
    global_rows: list[dict[str, Any]] = []
    circuit_rows: list[dict[str, Any]] = []
    for compound, group in slopes.groupby("compound", observed=True, sort=True):
        lower, upper, used_replicates = cluster_bootstrap_interval(
            group,
            replicates=bootstrap_replicates,
            seed=seed + len(global_rows),
        )
        global_rows.append(
            {
                "compound": str(compound),
                "pooled_slope_seconds_per_lap": _weighted_mean(group),
                "lower_95": lower,
                "upper_95": upper,
                "median_slope_seconds_per_lap": float(
                    group["slope_seconds_per_lap"].median()
                ),
                "negative_stint_slope_share": float(
                    group["slope_seconds_per_lap"].lt(0).mean()
                ),
                "stints": len(group),
                "races": group["race_id"].nunique(),
                "bootstrap_replicates": used_replicates,
                "weighting": "stint lap count",
            }
        )
    for (circuit, compound), group in slopes.groupby(
        ["circuit", "compound"], observed=True, sort=True
    ):
        races = group["race_id"].nunique()
        if races < MIN_CIRCUIT_RACES:
            continue
        lower, upper, used_replicates = cluster_bootstrap_interval(
            group,
            replicates=bootstrap_replicates,
            seed=seed + len(circuit_rows) + 10_000,
        )
        circuit_rows.append(
            {
                "circuit": str(circuit),
                "compound": str(compound),
                "pooled_slope_seconds_per_lap": _weighted_mean(group),
                "lower_95": lower,
                "upper_95": upper,
                "median_slope_seconds_per_lap": float(
                    group["slope_seconds_per_lap"].median()
                ),
                "stints": len(group),
                "races": races,
                "bootstrap_replicates": used_replicates,
                "pool_scope": "circuit-specific",
            }
        )
    circuit_pool = pd.DataFrame(circuit_rows)
    if not circuit_pool.empty:
        circuit_pool["pool_scope"] = "circuit-specific"
    return pd.DataFrame(global_rows), circuit_pool


def build_fixed_effects_design(
    race: pd.DataFrame,
    *,
    driver_stint_effect: bool = False,
) -> tuple[np.ndarray, list[str]]:
    """Build treatment-coded fixed effects and compound-specific age slopes."""
    driver_key = "stint_id" if driver_stint_effect else "driver_code"
    driver = pd.get_dummies(
        race[driver_key].astype(str), prefix=driver_key, drop_first=True, dtype=float
    )
    lap = pd.get_dummies(
        race["lap_number"].astype(str), prefix="race_lap", drop_first=True, dtype=float
    )
    compounds = sorted(race["compound"].astype(str).unique())
    compound_indicators = {
        compound: race["compound"].astype(str).eq(compound).to_numpy(dtype=float)
        for compound in compounds
    }
    parts = [np.ones((len(race), 1), dtype=float), driver.to_numpy(), lap.to_numpy()]
    names = ["Intercept", *driver.columns.tolist(), *lap.columns.tolist()]
    for compound in compounds[1:]:
        parts.append(compound_indicators[compound][:, None])
        names.append(f"compound[{compound}]")
    for compound in compounds:
        parts.append(
            (
                race["tyre_life"].to_numpy(dtype=float)
                * compound_indicators[compound]
            )[:, None]
        )
        names.append(f"tyre_life[{compound}]")
    return np.column_stack(parts), names


def _age_nuisance_residual(race: pd.DataFrame) -> float:
    """Measure how much tyre age remains after stint and race-lap effects."""
    stint = pd.get_dummies(
        race["stint_id"].astype(str), prefix="stint", drop_first=True, dtype=float
    )
    lap = pd.get_dummies(
        race["lap_number"].astype(str), prefix="lap", drop_first=True, dtype=float
    )
    nuisance = np.column_stack(
        [np.ones(len(race)), stint.to_numpy(), lap.to_numpy()]
    )
    age = race["tyre_life"].to_numpy(dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(nuisance, age, rcond=None)
    residual = age - nuisance @ coefficients
    return float(np.max(np.abs(residual)))


def diagnose_identifiability(
    laps: pd.DataFrame,
    fixed_status: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Show an actual-race rank proof for flawed and corrected designs."""
    eligible = laps.loc[~laps["mixed_compound_stint"]]
    chosen_race: pd.DataFrame | None = None
    chosen_id: str | None = None
    for race_id, race in eligible.groupby("race_id", sort=True):
        if race["compound"].nunique() < 2:
            continue
        chosen_race = race.copy()
        chosen_id = str(race_id)
        break
    if chosen_race is None or chosen_id is None:
        raise RuntimeError("No race has enough compound data for rank diagnostics.")

    flawed, _ = build_fixed_effects_design(chosen_race, driver_stint_effect=True)
    flawed_rank = int(np.linalg.matrix_rank(flawed))
    flawed_columns = int(flawed.shape[1])
    flawed_condition = float(np.linalg.cond(flawed))
    residual = _age_nuisance_residual(chosen_race)

    corrected, _ = build_fixed_effects_design(chosen_race, driver_stint_effect=False)
    corrected_rank = int(np.linalg.matrix_rank(corrected))
    corrected_columns = int(corrected.shape[1])
    corrected_condition = float(np.linalg.cond(corrected))
    if fixed_status is not None:
        rows = fixed_status.loc[fixed_status["race_id"].eq(chosen_id)]
        if not rows.empty:
            corrected_rank = int(rows["design_rank"].iloc[0])
            corrected_columns = int(rows["design_columns"].iloc[0])
            corrected_condition = float(rows["condition_number"].iloc[0])
    return {
        "race_id": chosen_id,
        "rows": len(chosen_race),
        "v2_design_rank": flawed_rank,
        "v2_design_columns": flawed_columns,
        "v2_condition_number": flawed_condition,
        "age_nuisance_max_absolute_residual": residual,
        "corrected_design_rank": corrected_rank,
        "corrected_design_columns": corrected_columns,
        "corrected_condition_number": corrected_condition,
        "corrected_design_full_rank": corrected_rank == corrected_columns,
    }


def fit_race_fixed_effects(
    laps: pd.DataFrame,
    fuel_effect_s_per_kg: float = DEFAULT_FUEL_EFFECT_S_PER_KG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit corrected race FE slopes only when the design has full column rank."""
    corrected_laps = apply_fuel_correction(laps, fuel_effect_s_per_kg)
    slope_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    for race_id, race in corrected_laps.groupby("race_id", sort=True):
        race = race.loc[~race["mixed_compound_stint"]].copy()
        try:
            design, names = build_fixed_effects_design(
                race, driver_stint_effect=False
            )
            rank = int(np.linalg.matrix_rank(design))
            columns = int(design.shape[1])
            condition = float(np.linalg.cond(design))
            status = {
                "race_id": str(race_id),
                "year": int(race["year"].iloc[0]),
                "round": int(race["round"].iloc[0]),
                "circuit": str(race["circuit"].iloc[0]),
                "laps": len(race),
                "design_rank": rank,
                "design_columns": columns,
                "condition_number": condition,
            }
            if rank != columns:
                status["status"] = "rank_deficient"
                status_rows.append(status)
                LOGGER.warning(
                    "Skipping race %s: corrected fixed-effects design rank %s/%s.",
                    race_id,
                    rank,
                    columns,
                )
                continue
            response = race["fuel_corrected_lap_time_seconds"].to_numpy(dtype=float)
            coefficients, _, _, _ = np.linalg.lstsq(design, response, rcond=None)
            residual = response - design @ coefficients
            degrees_freedom = len(response) - columns
            if degrees_freedom <= 0:
                status["status"] = "insufficient_residual_degrees_of_freedom"
                status_rows.append(status)
                continue
            variance = float(np.dot(residual, residual) / degrees_freedom)
            covariance = variance * np.linalg.inv(design.T @ design)
            for name, coefficient, parameter_variance in zip(
                names, coefficients, np.diag(covariance)
            ):
                if not name.startswith("tyre_life["):
                    continue
                compound = name.removeprefix("tyre_life[").removesuffix("]")
                group = race.loc[race["compound"].eq(compound)]
                slope_rows.append(
                    {
                        "race_id": str(race_id),
                        "year": int(group["year"].iloc[0]),
                        "round": int(group["round"].iloc[0]),
                        "circuit": str(group["circuit"].iloc[0]),
                        "compound": compound,
                        "slope_seconds_per_lap": float(coefficient),
                        "standard_error": float(math.sqrt(max(0.0, parameter_variance))),
                        "laps": len(group),
                    }
                )
            status["status"] = "full_rank"
            status_rows.append(status)
        except Exception as error:
            LOGGER.exception("Could not fit corrected fixed-effects race %s", race_id)
            status_rows.append(
                {
                    "race_id": str(race_id),
                    "year": int(race["year"].iloc[0]) if not race.empty else None,
                    "round": int(race["round"].iloc[0]) if not race.empty else None,
                    "circuit": str(race["circuit"].iloc[0]) if not race.empty else None,
                    "laps": len(race),
                    "status": f"failed: {type(error).__name__}: {error}",
                    "reason": f"{type(error).__name__}: {error}",
                }
            )
    return pd.DataFrame(slope_rows), pd.DataFrame(status_rows)


def pool_race_slopes(slopes: pd.DataFrame) -> pd.DataFrame:
    """Combine identifiable race slopes with a DerSimonian-Laird pool."""
    rows: list[dict[str, Any]] = []
    if slopes.empty:
        return pd.DataFrame()
    for compound, group in slopes.groupby("compound", observed=True, sort=True):
        estimate = group["slope_seconds_per_lap"].to_numpy(dtype=float)
        variance = np.square(group["standard_error"].to_numpy(dtype=float))
        good = np.isfinite(estimate) & np.isfinite(variance) & (variance > 0)
        estimate = estimate[good]
        variance = variance[good]
        if not len(estimate):
            continue
        weights = 1.0 / variance
        fixed = float(np.sum(weights * estimate) / np.sum(weights))
        q_value = float(np.sum(weights * np.square(estimate - fixed)))
        c_value = float(np.sum(weights) - np.sum(weights**2) / np.sum(weights))
        tau_squared = (
            max(0.0, (q_value - (len(estimate) - 1)) / c_value)
            if len(estimate) > 1 and c_value > 0
            else 0.0
        )
        random_weights = 1.0 / (variance + tau_squared)
        pooled = float(np.sum(random_weights * estimate) / np.sum(random_weights))
        standard_error = float(math.sqrt(1.0 / np.sum(random_weights)))
        rows.append(
            {
                "compound": str(compound),
                "pooled_slope_seconds_per_lap": pooled,
                "lower_95": pooled - 1.96 * standard_error,
                "upper_95": pooled + 1.96 * standard_error,
                "race_estimates": len(estimate),
                "negative_slope_share": float(np.mean(estimate < 0)),
                "tau_squared": tau_squared,
            }
        )
    return pd.DataFrame(rows)


def make_synthetic_races(
    *,
    seed: int = 7421,
    race_count: int = 12,
    driver_count: int = 20,
    race_laps: int = 60,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Create pit-strategy races with known wear, fuel, pace and lap noise."""
    generator = np.random.default_rng(seed)
    truth = {"SOFT": 0.10, "MEDIUM": 0.06, "HARD": 0.03}
    rows: list[dict[str, Any]] = []
    fuel_effect = DEFAULT_FUEL_EFFECT_S_PER_KG
    fuel_per_lap = 110.0 / race_laps
    for race_number in range(race_count):
        race_id = f"synthetic-{race_number + 1}"
        for driver_number in range(driver_count):
            first_stop = int(generator.integers(13, 20))
            second_stop = int(generator.integers(33, 45))
            boundaries = (1, first_stop + 1, second_stop + 1, race_laps + 1)
            compounds = (
                COMPOUND_ORDER[driver_number % 3],
                COMPOUND_ORDER[(driver_number + 1) % 3],
                COMPOUND_ORDER[(driver_number + 2) % 3],
            )
            driver_pace = float(generator.normal(0.0, 0.8))
            initial_age = int(generator.integers(1, 5))
            for stint_index, compound in enumerate(compounds):
                start = boundaries[stint_index]
                end = boundaries[stint_index + 1]
                starting_age = initial_age if stint_index == 0 else 1
                for race_lap in range(start, end):
                    age = starting_age + race_lap - start
                    remaining_fuel = 110.0 - fuel_per_lap * (race_lap - 1)
                    observed = (
                        82.0
                        + race_number * 0.12
                        + driver_pace
                        + remaining_fuel * fuel_effect
                        + truth[compound] * (age - 1)
                        + float(generator.normal(0.0, 0.22))
                    )
                    rows.append(
                        {
                            "year": 2030 + race_number // 20,
                            "round": race_number + 1,
                            "circuit": f"Synthetic Circuit {race_number % 4}",
                            "driver_code": f"D{driver_number:02d}",
                            "compound": compound,
                            "tyre_life": age,
                            "stint_number": stint_index + 1,
                            "lap_number": race_lap,
                            "lap_time_seconds": observed,
                            "race_laps": race_laps,
                            "race_id": race_id,
                            "stint_id": f"{race_id}|D{driver_number:02d}|{stint_index + 1}",
                            "stint_lap_number": race_lap - start + 1,
                            "mixed_compound_stint": False,
                        }
                    )
    return pd.DataFrame(rows), truth


def synthetic_recovery_experiment() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the primary, corrected-FE and flawed-v2 methods on known data."""
    synthetic, truth = make_synthetic_races()
    stint_slopes, _ = fit_stint_slopes(synthetic, DEFAULT_FUEL_EFFECT_S_PER_KG)
    pooled, _ = pool_stint_slopes(
        stint_slopes, bootstrap_replicates=BOOTSTRAP_REPLICATES, seed=9182
    )
    fixed_slopes, fixed_status = fit_race_fixed_effects(
        synthetic, DEFAULT_FUEL_EFFECT_S_PER_KG
    )
    fixed_pool = pool_race_slopes(fixed_slopes)
    fixed_pool_by_compound = fixed_pool.set_index("compound").to_dict("index")
    primary_by_compound = pooled.set_index("compound").to_dict("index")
    rows: list[dict[str, Any]] = []
    for compound in COMPOUND_ORDER:
        rows.append(
            {
                "method": "Primary stint slopes",
                "compound": compound,
                "true_slope": truth[compound],
                "recovered_slope": primary_by_compound[compound][
                    "pooled_slope_seconds_per_lap"
                ],
                "error": (
                    primary_by_compound[compound]["pooled_slope_seconds_per_lap"]
                    - truth[compound]
                ),
                "full_rank_races": int(fixed_status["status"].eq("full_rank").sum()),
            }
        )
        fixed = fixed_pool_by_compound.get(compound)
        rows.append(
            {
                "method": "Corrected race fixed effects",
                "compound": compound,
                "true_slope": truth[compound],
                "recovered_slope": (
                    fixed["pooled_slope_seconds_per_lap"]
                    if fixed is not None
                    else float("nan")
                ),
                "error": (
                    fixed["pooled_slope_seconds_per_lap"] - truth[compound]
                    if fixed is not None
                    else float("nan")
                ),
                "full_rank_races": int(fixed_status["status"].eq("full_rank").sum()),
            }
        )
    flawed_race = synthetic.loc[synthetic["race_id"].eq("synthetic-1")]
    flawed_design, _ = build_fixed_effects_design(
        flawed_race, driver_stint_effect=True
    )
    flawed_rank = int(np.linalg.matrix_rank(flawed_design))
    rows.append(
        {
            "method": "Flawed v2 design",
            "compound": "all",
            "true_slope": float("nan"),
            "recovered_slope": float("nan"),
            "error": float("nan"),
            "full_rank_races": int(flawed_rank == flawed_design.shape[1]),
            "rank": flawed_rank,
            "columns": int(flawed_design.shape[1]),
        }
    )
    primary_recovery = pd.DataFrame(rows)
    details = {
        "truth": truth,
        "primary_slopes": stint_slopes,
        "primary_pools": pooled,
        "fixed_slopes": fixed_slopes,
        "fixed_status": fixed_status,
        "flawed_v2_rank": flawed_rank,
        "flawed_v2_columns": int(flawed_design.shape[1]),
        "synthetic_rows": len(synthetic),
    }
    return primary_recovery, details


def _pool_training_stints(slopes: pd.DataFrame) -> dict[str, float]:
    pools: dict[str, float] = {}
    for compound, group in slopes.groupby("compound", observed=True):
        pools[str(compound)] = _weighted_mean(group)
    return pools


def _stint_relative_rows(laps: pd.DataFrame) -> pd.DataFrame:
    """Make corrected lap times relative to the first three clean laps."""
    corrected = laps.sort_values(["stint_id", "lap_number"]).copy()
    baseline = corrected.groupby("stint_id", sort=False).head(3).groupby(
        "stint_id", sort=False
    )["fuel_corrected_lap_time_seconds"].median()
    baseline_age = corrected.groupby("stint_id", sort=False).head(3).groupby(
        "stint_id", sort=False
    )["tyre_life"].median()
    corrected["stint_reference_time"] = corrected["stint_id"].map(baseline)
    corrected["stint_reference_age"] = corrected["stint_id"].map(baseline_age)
    corrected["relative_time_seconds"] = (
        corrected["fuel_corrected_lap_time_seconds"]
        - corrected["stint_reference_time"]
    )
    corrected["relative_tyre_age"] = (
        corrected["tyre_life"] - corrected["stint_reference_age"]
    )
    return corrected


def _evaluate_fold(
    test_laps: pd.DataFrame,
    train_slopes: pd.DataFrame,
) -> dict[str, Any]:
    test_slopes, _ = fit_stint_slopes(test_laps, DEFAULT_FUEL_EFFECT_S_PER_KG)
    if test_slopes.empty:
        return {
            "laps": 0,
            "stints": 0,
            "baseline_relative_mae": float("nan"),
            "model_relative_mae": float("nan"),
            "baseline_slope_mae": float("nan"),
            "model_slope_mae": float("nan"),
            "plausible_observed_slope_share": float("nan"),
            "unpooled_stints": 0,
        }
    pools = _pool_training_stints(train_slopes) if not train_slopes.empty else {}
    eval_laps = apply_fuel_correction(test_laps, DEFAULT_FUEL_EFFECT_S_PER_KG)
    eval_laps = _stint_relative_rows(eval_laps)
    eligible_ids = set(test_slopes["stint_id"])
    eval_laps = eval_laps.loc[eval_laps["stint_id"].isin(eligible_ids)].copy()
    eval_laps["predicted_slope"] = eval_laps["compound"].map(pools)
    missing_pool = eval_laps["predicted_slope"].isna()
    unpooled_stints = int(eval_laps.loc[missing_pool, "stint_id"].nunique())
    eval_laps["predicted_slope"] = eval_laps["predicted_slope"].fillna(0.0)
    eval_laps["predicted_relative_time"] = (
        eval_laps["predicted_slope"] * eval_laps["relative_tyre_age"]
    )
    per_stint = eval_laps.groupby("stint_id", sort=False).agg(
        compound=("compound", "first"),
        actual_relative=("relative_time_seconds", list),
        predicted_relative=("predicted_relative_time", list),
        observed_slope=("tyre_life", "size"),
    )
    observed_slopes = test_slopes.set_index("stint_id")["slope_seconds_per_lap"]
    per_stint["observed_slope"] = observed_slopes
    predicted_slopes = per_stint["compound"].map(pools).fillna(0.0)
    slope_errors = predicted_slopes - per_stint["observed_slope"]
    actual_values = np.concatenate(per_stint["actual_relative"].to_list())
    predicted_values = np.concatenate(per_stint["predicted_relative"].to_list())
    zero_mae = float(np.mean(np.abs(actual_values)))
    model_mae = float(np.mean(np.abs(actual_values - predicted_values)))
    return {
        "laps": len(eval_laps),
        "stints": len(per_stint),
        "baseline_relative_mae": zero_mae,
        "model_relative_mae": model_mae,
        "baseline_slope_mae": float(np.mean(np.abs(per_stint["observed_slope"]))),
        "model_slope_mae": float(np.mean(np.abs(slope_errors))),
        "plausible_observed_slope_share": float(
            per_stint["observed_slope"].between(0.0, 0.5, inclusive="neither").mean()
        ),
        "unpooled_stints": unpooled_stints,
    }


def evaluate_primary_method(
    laps: pd.DataFrame,
    slopes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate zero and stint-pool predictions by race and held-out season."""
    race_rows: list[dict[str, Any]] = []
    races = sorted(laps["race_id"].unique())
    for race_id in races:
        training_slopes = slopes.loc[slopes["race_id"].ne(race_id)]
        testing_laps = laps.loc[laps["race_id"].eq(race_id)]
        metrics = _evaluate_fold(testing_laps, training_slopes)
        race_rows.append(
            {
                "race_id": race_id,
                "year": int(testing_laps["year"].iloc[0]),
                "round": int(testing_laps["round"].iloc[0]),
                "circuit": str(testing_laps["circuit"].iloc[0]),
                **metrics,
            }
        )
    race_results = pd.DataFrame(race_rows)
    race_summary = pd.DataFrame(
        [
            {
                "validation": "leave-one-race-out",
                "races": len(race_results),
                "baseline_relative_mae_seconds": float(
                    race_results["baseline_relative_mae"].mean()
                ),
                "model_relative_mae_seconds": float(
                    race_results["model_relative_mae"].mean()
                ),
                "baseline_stint_slope_mae_seconds_per_lap": float(
                    race_results["baseline_slope_mae"].mean()
                ),
                "model_stint_slope_mae_seconds_per_lap": float(
                    race_results["model_slope_mae"].mean()
                ),
                "plausible_observed_slope_share": float(
                    race_results["plausible_observed_slope_share"].mean()
                ),
                "unpooled_stints": int(race_results["unpooled_stints"].sum()),
            }
        ]
    )

    train_laps = laps.loc[laps["year"].lt(2024)]
    test_laps = laps.loc[laps["year"].eq(2024)]
    train_slopes = slopes.loc[slopes["year"].lt(2024)]
    if train_laps.empty or test_laps.empty:
        raise ValueError("Chronological validation requires 2022-2023 train and 2024 test.")
    seasonal_metrics = _evaluate_fold(test_laps, train_slopes)
    season_summary = pd.DataFrame(
        [
            {
                "validation": "train 2022-2023, test 2024",
                "races": test_laps["race_id"].nunique(),
                "baseline_relative_mae_seconds": seasonal_metrics[
                    "baseline_relative_mae"
                ],
                "model_relative_mae_seconds": seasonal_metrics[
                    "model_relative_mae"
                ],
                "baseline_stint_slope_mae_seconds_per_lap": seasonal_metrics[
                    "baseline_slope_mae"
                ],
                "model_stint_slope_mae_seconds_per_lap": seasonal_metrics[
                    "model_slope_mae"
                ],
                "plausible_observed_slope_share": seasonal_metrics[
                    "plausible_observed_slope_share"
                ],
                "unpooled_stints": seasonal_metrics["unpooled_stints"],
            }
        ]
    )
    return race_summary, race_results, season_summary


def _compound_ordering(pools: pd.DataFrame) -> dict[str, Any]:
    """Report nominal pooled ordering and complete compounds present."""
    by_compound = pools.set_index("compound")["pooled_slope_seconds_per_lap"]
    if not set(COMPOUND_ORDER).issubset(by_compound.index):
        return {"holds": False, "reason": "one or more nominated compounds lack data"}
    soft, medium, hard = (float(by_compound[name]) for name in COMPOUND_ORDER)
    return {
        "holds": bool(soft > medium > hard),
        "soft": soft,
        "medium": medium,
        "hard": hard,
    }


def _pool_maps(
    global_pools: pd.DataFrame,
    circuit_pools: pd.DataFrame,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    global_map = {
        str(row.compound): {
            "slope": float(row.pooled_slope_seconds_per_lap),
            "lower": float(row.lower_95),
            "upper": float(row.upper_95),
            "races": int(row.races),
        }
        for row in global_pools.itertuples(index=False)
    }
    circuit_map = {
        f"{row.circuit}|{row.compound}": {
            "slope": float(row.pooled_slope_seconds_per_lap),
            "lower": float(row.lower_95),
            "upper": float(row.upper_95),
            "races": int(row.races),
        }
        for row in circuit_pools.itertuples(index=False)
    }
    return global_map, circuit_map


def build_artifact(
    primary_slopes: pd.DataFrame,
    *,
    max_tyre_age_by_compound: dict[str, int],
) -> dict[str, Any]:
    """Prepare a joblib-safe artifact using the default fuel assumption."""
    global_pools, circuit_pools = pool_stint_slopes(primary_slopes)
    global_map, circuit_map = _pool_maps(global_pools, circuit_pools)
    return {
        "model_version": MODEL_VERSION,
        "model_name": "Stint-level OLS slopes with race-cluster bootstrap",
        "fuel_effect_s_per_kg": DEFAULT_FUEL_EFFECT_S_PER_KG,
        "weighting": "stint lap count",
        "minimum_stint_laps": MIN_STINT_LAPS,
        "global": global_map,
        "circuits": circuit_map,
        "max_tyre_age_by_compound": max_tyre_age_by_compound,
    }


def predict_relative_degradation(
    circuit: str,
    compound: str,
    tyre_life: int,
    *,
    model_path: str | Path = MODEL_PATH,
) -> tuple[float, float, float, bool]:
    """Return expected lap-time loss, its 95% range, and a reliability flag.

    A circuit-specific pool requires at least three race clusters. If unavailable,
    this function uses the cross-circuit pool and emits a warning. A point
    estimate is never clipped: negative fitted values remain visible. Reliability
    is false whenever the interval contains zero or a circuit fallback is used.
    Drivers often pit before tyres fall off, so old observed tyres are selected
    survivors; this survivorship bias limits interpretation.
    """
    if not isinstance(circuit, str) or not circuit.strip():
        raise ValueError("Circuit must be a non-empty event name.")
    if compound not in KNOWN_COMPOUNDS:
        raise ValueError(f"Compound must be one of {KNOWN_COMPOUNDS}.")
    if isinstance(tyre_life, bool) or not isinstance(tyre_life, (int, np.integer)):
        raise TypeError("Tyre life must be an integer.")
    if tyre_life < 1:
        raise ValueError("Tyre life must be at least one lap.")
    artifact_path = Path(model_path)
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Saved v3 degradation model not found: {artifact_path}")
    artifact = joblib.load(artifact_path)
    if not isinstance(artifact, dict) or artifact.get("model_version") != MODEL_VERSION:
        raise ValueError(f"Unsupported v3 degradation artifact: {artifact_path}")
    key = f"{circuit}|{compound}"
    estimate = artifact["circuits"].get(key)
    fallback = estimate is None
    if fallback:
        estimate = artifact["global"].get(compound)
        if estimate is None:
            raise ValueError(f"No pooled estimate is available for {compound}.")
        warnings.warn(
            f"No circuit pool with at least {MIN_CIRCUIT_RACES} races for "
            f"{circuit}/{compound}; using the cross-circuit pool.",
            RuntimeWarning,
            stacklevel=2,
        )
    age_difference = float(tyre_life - 1)
    point = float(estimate["slope"] * age_difference)
    endpoints = sorted(
        (
            float(estimate["lower"] * age_difference),
            float(estimate["upper"] * age_difference),
        )
    )
    lower, upper = endpoints
    if not all(math.isfinite(value) for value in (point, lower, upper)):
        raise RuntimeError("The saved degradation model returned non-finite predictions.")
    if not lower <= point <= upper:
        raise RuntimeError("The saved uncertainty range does not contain its estimate.")
    reliable = bool(lower > 0 or upper < 0) and not fallback
    if not reliable and not fallback:
        warnings.warn(
            f"The 95% interval includes zero for {circuit}/{compound}; "
            "treat this prediction as unreliable.",
            RuntimeWarning,
            stacklevel=2,
        )
    return point, lower, upper, reliable


def cliff_planning_lap(
    circuit: str,
    compound: str,
    *,
    loss_threshold_seconds: float = 1.0,
    model_path: str | Path = MODEL_PATH,
) -> int | None:
    """Return a linear planning threshold, not a detected physical cliff.

    Survivorship bias means drivers may pit before a tyre's actual fall-off is
    observed. This threshold should not be read as a measured wear cliff.
    """
    if not math.isfinite(loss_threshold_seconds) or loss_threshold_seconds <= 0:
        raise ValueError("The planning threshold must be positive and finite.")
    artifact = joblib.load(model_path)
    key = f"{circuit}|{compound}"
    estimate = artifact["circuits"].get(key)
    if estimate is None:
        estimate = artifact["global"].get(compound)
        if estimate is None:
            raise ValueError(f"No pooled estimate is available for {compound}.")
        warnings.warn(
            f"No circuit pool with at least {MIN_CIRCUIT_RACES} races for "
            f"{circuit}/{compound}; using the cross-circuit pool.",
            RuntimeWarning,
            stacklevel=2,
        )
    slope = float(estimate["slope"])
    if slope <= 0:
        return None
    age = int(math.ceil(loss_threshold_seconds / slope)) + 1
    if age > int(artifact["max_tyre_age_by_compound"].get(compound, 0)):
        return None
    return age


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render Markdown tables without requiring optional tabulate."""
    if frame.empty:
        return "_No eligible estimates._"
    headers = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in frame.itertuples(index=False, name=None):
        values: list[str] = []
        for value in row:
            if pd.isna(value):
                values.append("—")
            elif isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.4f}")
            else:
                values.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def run_analysis() -> dict[str, Any]:
    """Run fuel sensitivity, both estimators, recovery, validation and reports."""
    raw_laps = load_laps()
    laps, exclusions = prepare_laps(raw_laps)
    exclusion_audit = dict(exclusions)
    all_stint_slopes: dict[float, pd.DataFrame] = {}
    stint_audits: dict[float, dict[str, int]] = {}
    pooled_tables: list[pd.DataFrame] = []
    circuit_tables: list[pd.DataFrame] = []
    for setting_index, fuel_effect in enumerate(FUEL_EFFECT_SETTINGS):
        slopes, audit = fit_stint_slopes(laps, fuel_effect)
        all_stint_slopes[fuel_effect] = slopes
        stint_audits[fuel_effect] = audit
        global_pool, circuit_pool = pool_stint_slopes(
            slopes,
            seed=20261106 + setting_index * 1000,
        )
        global_pool.insert(0, "fuel_effect_s_per_kg", fuel_effect)
        if not circuit_pool.empty:
            circuit_pool.insert(0, "fuel_effect_s_per_kg", fuel_effect)
        pooled_tables.append(global_pool)
        circuit_tables.append(circuit_pool)

    default_slopes = all_stint_slopes[DEFAULT_FUEL_EFFECT_S_PER_KG]
    fixed_slopes, fixed_status = fit_race_fixed_effects(laps)
    fixed_pools = pool_race_slopes(fixed_slopes)
    diagnostics = diagnose_identifiability(laps, fixed_status)
    recovery, recovery_details = synthetic_recovery_experiment()
    race_eval, per_race_eval, season_eval = evaluate_primary_method(
        laps, default_slopes
    )

    default_pool = pooled_tables[FUEL_EFFECT_SETTINGS.index(DEFAULT_FUEL_EFFECT_S_PER_KG)].copy()
    ordering_rows: list[dict[str, Any]] = []
    for setting, pool in zip(FUEL_EFFECT_SETTINGS, pooled_tables):
        ordering = _compound_ordering(pool)
        for _, row in pool.iterrows():
            ordering_rows.append(
                {
                    "fuel_effect_s_per_kg": setting,
                    **row.to_dict(),
                    "pooled_SOFT_gt_MEDIUM_gt_HARD": ordering["holds"],
                }
            )
    sensitivity_table = pd.DataFrame(ordering_rows)

    max_age = (
        laps.groupby("compound", observed=True)["tyre_life"]
        .max()
        .astype(int)
        .to_dict()
    )
    artifact = build_artifact(
        default_slopes,
        max_tyre_age_by_compound={str(k): int(v) for k, v in max_age.items()},
    )
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH, compress=3)

    excluded_short = int(
        sum(audit["stints_shorter_than_minimum_for_this_setting"] for audit in stint_audits.values())
        / len(stint_audits)
    )
    exclusions["stints_shorter_than_8_clean_laps"] = excluded_short
    exclusions["stints_with_multiple_compounds"] = int(
        laps.loc[laps["mixed_compound_stint"], "stint_id"].nunique()
    )
    exclusions["laps_removed_by_optional_slow_lap_filter"] = 0
    rank_failures = fixed_status.loc[fixed_status["status"].eq("rank_deficient")]
    fixed_fit_failures = fixed_status.loc[
        fixed_status["status"].astype(str).str.startswith("failed:")
    ]
    summary = {
        "input_rows": len(raw_laps),
        "usable_rows": len(laps),
        "races": int(laps["race_id"].nunique()),
        "rows_excluded": int(exclusions["rows_excluded_missing_or_invalid_required_fields"]),
        "stints_fitted_at_default": len(default_slopes),
        "eligible_stint_slope_negative_share": float(
            default_slopes["slope_seconds_per_lap"].lt(0).mean()
        ),
        "eligible_stint_slope_plausible_share": float(
            default_slopes["slope_seconds_per_lap"].between(
                0.0, 0.5, inclusive="neither"
            ).mean()
        ),
        "fixed_effects_full_rank_races": int(fixed_status["status"].eq("full_rank").sum()),
        "fixed_effects_rank_deficient_races": len(rank_failures),
        "fixed_effects_failed_races": len(fixed_fit_failures),
        "correlation_tyre_age_stint_lap": float(
            laps["tyre_life"].corr(laps["stint_lap_number"])
        ),
    }
    report = _make_report(
        summary=summary,
        exclusions=exclusions,
        stint_audits=stint_audits,
        diagnostics=diagnostics,
        sensitivity_table=sensitivity_table,
        circuit_pools=pd.concat(circuit_tables, ignore_index=True)
        if any(not table.empty for table in circuit_tables)
        else pd.DataFrame(),
        fixed_slopes=fixed_slopes,
        fixed_status=fixed_status,
        fixed_pools=fixed_pools,
        recovery=recovery,
        race_eval=race_eval,
        per_race_eval=per_race_eval,
        season_eval=season_eval,
    )
    (PROJECT_ROOT / "docs" / "results_v3.md").write_text(report, encoding="utf-8")
    (PROJECT_ROOT / "docs" / "model_results.md").write_text(report, encoding="utf-8")
    return {
        "raw_laps": raw_laps,
        "laps": laps,
        "exclusions": exclusions,
        "stint_slopes_by_fuel": all_stint_slopes,
        "stint_audits": stint_audits,
        "pooled_by_fuel": pd.concat(pooled_tables, ignore_index=True),
        "circuit_pools_by_fuel": pd.concat(circuit_tables, ignore_index=True)
        if any(not table.empty for table in circuit_tables)
        else pd.DataFrame(),
        "sensitivity_table": sensitivity_table,
        "fixed_slopes": fixed_slopes,
        "fixed_status": fixed_status,
        "fixed_pools": fixed_pools,
        "identifiability": diagnostics,
        "synthetic_recovery": recovery,
        "synthetic_details": recovery_details,
        "race_evaluation": race_eval,
        "per_race_evaluation": per_race_eval,
        "season_evaluation": season_eval,
        "summary": summary,
        "artifact_path": MODEL_PATH,
    }


def _make_report(
    *,
    summary: dict[str, Any],
    exclusions: dict[str, Any],
    stint_audits: dict[float, dict[str, int]],
    diagnostics: dict[str, Any],
    sensitivity_table: pd.DataFrame,
    circuit_pools: pd.DataFrame,
    fixed_slopes: pd.DataFrame,
    fixed_status: pd.DataFrame,
    fixed_pools: pd.DataFrame,
    recovery: pd.DataFrame,
    race_eval: pd.DataFrame,
    per_race_eval: pd.DataFrame,
    season_eval: pd.DataFrame,
) -> str:
    """Write all requested caveats and observable counts into one report."""
    eligible_slow = int(summary["rows_excluded"])
    recent_before = (
        2.283070,
        9.335910,
        9.334432,
        2.989151,
    )
    zero_race = float(race_eval.iloc[0]["baseline_relative_mae_seconds"])
    model_race = float(race_eval.iloc[0]["model_relative_mae_seconds"])
    zero_season = float(season_eval.iloc[0]["baseline_relative_mae_seconds"])
    model_season = float(season_eval.iloc[0]["model_relative_mae_seconds"])
    slopes_default = sensitivity_table.loc[
        sensitivity_table["fuel_effect_s_per_kg"].eq(DEFAULT_FUEL_EFFECT_S_PER_KG)
    ]
    comparison = pd.DataFrame(
        [
            {
                "version": "v1 absolute-time models",
                "LO-race relative MAE": "not measured; absolute MAE is incomparable",
                "2024 relative MAE": "not measured",
                "slope status": "25/60 negative; old exploratory estimates",
            },
            {
                "version": "v2 flawed race FE",
                "LO-race relative MAE": "1.1356 s (worse than 1.0986 s zero baseline)",
                "2024 relative MAE": "0.9980 s (worse than 0.8867 s zero baseline)",
                "slope status": "invalid; 66/66 designs rank deficient",
            },
            {
                "version": "v3 stint slope",
                "LO-race relative MAE": f"{model_race:.4f} s vs zero {zero_race:.4f} s",
                "2024 relative MAE": f"{model_season:.4f} s vs zero {zero_season:.4f} s",
                "slope status": f"{summary['eligible_stint_slope_negative_share']:.1%} negative, "
                f"{summary['eligible_stint_slope_plausible_share']:.1%} in (0, 0.5)",
            },
        ]
    )
    report = f"""# Tyre degradation v3: fuel-corrected stint slopes

## What changed

The v2 design is invalid. It used driver-stint fixed effects and race-lap fixed
effects together. Within a stint, tyre age changes by exactly the same amount
as race lap, so those fixed effects absorb all independent age variation. V2's
66/66 rank-deficient slope estimates are numerical artifacts, not findings.
The full v2 report is preserved in [results_v2_flawed.md](results_v2_flawed.md).

V3's primary method fits an ordinary least-squares line to fuel-corrected lap
time versus tyre age within each stint of at least {MIN_STINT_LAPS} clean laps.
It pools stint slopes by stint lap count and uses a cluster bootstrap that
resamples entire races for 95% intervals. This avoids treating stints in a
shared race as independent bootstrap samples. No 3%-slow-lap filtering was
applied; all eligible clean laps were retained.

## Fuel assumption and correction sign

For each race, fuel per lap is estimated as 110 kg divided by the maximum lap
number. The assumed lap-time effect is {DEFAULT_FUEL_EFFECT_S_PER_KG:.2f}
seconds per kg, with {', '.join(f'{rate:.2f}' for rate in FUEL_EFFECT_SETTINGS)}
seconds per kg as the sensitivity band. These are approximate assumptions,
not measured fuel burn or car-specific coefficients.

The correction is
`corrected_time = observed_time + fuel_per_lap_kg * fuel_effect_s_per_kg * (lap - 1)`.
The sign is positive: a later lap is faster because it carries less fuel, so
we add that estimated time penalty to express it at the starting fuel load.
For example, with 60 race laps and 0.03 s/kg, the per-lap fuel change is
1.833 kg and each lap after lap 1 receives +0.055 s. Subtracting that positive
amount would move the lap in the wrong direction.

## Data accounting and diagnostics

- Source rows: {summary['input_rows']:,}; used rows: {summary['usable_rows']:,};
  excluded for missing/invalid required fields: {eligible_slow:,}.
- Missing values by field: {exclusions['missing_values_by_field']}.
- Invalid numeric values by field: {exclusions['invalid_numeric_by_field']}.
- Unknown compound labels retained for the nominal analyses:
  {exclusions['source_rows_with_unknown_compounds']}.
- Stints shorter than 8 clean laps: {exclusions['stints_shorter_than_8_clean_laps']};
  multi-compound stints: {exclusions['stints_with_multiple_compounds']};
  stints with no tyre-age variation: {sum(item['stints_without_tyre_age_variation'] for item in stint_audits.values()) // len(stint_audits)}.
- Laps removed by optional >3%-slower-than-median filter: **0** (filter disabled).
- Correlation of tyre age with within-stint lap number:
  **r={summary['correlation_tyre_age_stint_lap']:.4f}**. This high value is
  expected because tyre age usually advances once per lap until a pit stop
  resets it. It is not itself a bug; the important distinction is that V3
  estimates a slope within each stint rather than trying to estimate that
  slope alongside a separate fixed effect for every stint.

## Proof of the v2 identification problem

Actual race used for the diagnostic: {diagnostics['race_id']} ({diagnostics['rows']:,} laps).
The v2 design rank is {diagnostics['v2_design_rank']} for
{diagnostics['v2_design_columns']} columns; its condition number is
{diagnostics['v2_condition_number']:.4g}. Regressing tyre age on just the
driver-stint and race-lap fixed-effect columns leaves a maximum absolute
residual of {diagnostics['age_nuisance_max_absolute_residual']:.3g} laps.
Thus, age is an exact (to floating-point precision) linear combination of the
effects; its interaction with compound cannot be separately identified.

The corrected design uses one driver effect per driver, not per stint, with
race-lap effects, compound intercepts, and tyre-age-by-compound terms. For
{diagnostics['race_id']} its rank is {diagnostics['corrected_design_rank']} of
{diagnostics['corrected_design_columns']}, condition number
{diagnostics['corrected_condition_number']:.4g}, and full-rank status is
**{diagnostics['corrected_design_full_rank']}**. Across observed races,
{summary['fixed_effects_full_rank_races']} were full rank,
{summary['fixed_effects_rank_deficient_races']} were rank deficient, and
{summary['fixed_effects_failed_races']} failed. Rank-deficient races are not
reported as having slopes.

## Primary stint slope estimates

Weights are stint lap counts. Intervals below are percentile 95% intervals
from {BOOTSTRAP_REPLICATES:,} whole-race bootstrap resamples per compound.
The following table reports the required fuel sensitivity; negative slopes
remain visible.

{_markdown_table(sensitivity_table[['fuel_effect_s_per_kg','compound','pooled_slope_seconds_per_lap','lower_95','upper_95','median_slope_seconds_per_lap','negative_stint_slope_share','stints','races','pooled_SOFT_gt_MEDIUM_gt_HARD']])}

Circuit pools are shown only when at least {MIN_CIRCUIT_RACES} distinct races
contribute; other circuit/compound combinations use the cross-circuit pool
and are flagged as fallbacks by the API.

{_markdown_table(circuit_pools)}

### Corrected race fixed-effects cross-check

This model uses one driver fixed effect per race, race-lap fixed effects,
compound intercepts, and a separate tyre-age slope for each compound. A race
is used only if its design has full column rank.

Rank/failure status by race:

{_markdown_table(fixed_status[['race_id','circuit','status','design_rank','design_columns','condition_number']])}

Random-effects pooled cross-check slopes:

{_markdown_table(fixed_pools)}

The cross-check is not the primary estimate. Its coverage is limited to the
full-rank races listed above.

## Synthetic parameter recovery

Synthetic races have known degradation rates (SOFT 0.10, MEDIUM 0.06, HARD
0.03 s/lap), 110 kg starting fuel, the assumed 0.03 s/kg fuel effect, driver
pace differences, varied pit schedules, used-tyre starting ages, and 0.22 s
lap noise.

{_markdown_table(recovery)}

The primary method is considered to recover synthetic truth only when each
pooled estimate is within 0.03 s/lap of its known slope. The flawed v2 design
is not assigned a recovered slope when rank deficient.

## Out-of-sample evaluation

No random split is used. Leave-one-race-out withholds all laps and stints from
each race. The chronological holdout trains on 2022-2023 and tests on 2024.
The relative lap target is fuel-corrected time minus that stint's first-three-
clean-lap median. Slope error compares each held-out stint's prediction with
that stint's directly observed OLS slope. The zero baseline predicts no
relative degradation and a slope of zero.

Leave-one-race-out summary:

{_markdown_table(race_eval)}

Chronological summary:

{_markdown_table(season_eval)}

Per-race leave-one-out errors:

{_markdown_table(per_race_eval)}

## Before and after

The v1 absolute-time errors cannot be compared directly to v2/v3 relative-time
errors. The v1 absolute MAEs were naive 2.2831 s, pooled linear 9.3359 s,
MixedLM 9.3344 s, and gradient boosting 2.9892 s. V2's relative-target result
was worse than its zero baseline and its slopes are invalid as explained above.

{_markdown_table(comparison)}

## Limitations and conclusion

This model is **not validated** unless it both recovers synthetic truth and
beats the zero-degradation baseline with intervals excluding zero. Synthetic
recovery results are shown above; the real-data MAE comparison determines
whether it beats the baseline. Some compound intervals may include zero, and
the compounds are only the weekend-relative SOFT/MEDIUM/HARD labels, not the
underlying Pirelli C1-C5 rubber.

Fuel effects and the 110 kg starting load are approximate, not measured.
Stint-level slopes can still absorb track evolution, traffic, weather, setup,
and tyre management. The minimum eight-lap rule excludes shorter stints and is
counted above. Drivers often pit before tyres fall off, creating survivorship
bias. Circuit pools with fewer than three race clusters fall back to the
cross-circuit estimate. Do not treat these exploratory estimates as causal
wear rates or pit-strategy advice.

No schema changes were made. The v3 artifact is
`models/tyre_degradation_v3.joblib`.
"""
    return report


def main() -> None:
    """Run v3 from the command line and print concise measured summaries."""
    results = run_analysis()
    print("Tyre degradation v3 analysis complete.")
    print(f"Input rows: {results['summary']['input_rows']:,}")
    print(f"Rows excluded for required fields: {results['summary']['rows_excluded']:,}")
    print("\nFuel-sensitivity primary pools:")
    print(results["sensitivity_table"].to_string(index=False))
    print("\nCorrected race fixed-effects pools:")
    print(results["fixed_pools"].to_string(index=False))
    print("\nSynthetic recovery:")
    print(results["synthetic_recovery"].to_string(index=False))
    print("\nEvaluation:")
    print(results["race_evaluation"].to_string(index=False))
    print(results["season_evaluation"].to_string(index=False))
    print(f"\nArtifact: {results['artifact_path']}")
    print("Reports: docs/results_v3.md and docs/model_results.md")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
