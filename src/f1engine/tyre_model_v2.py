"""Stint-relative tyre-wear analysis with race and stint fixed effects."""

from __future__ import annotations

import logging
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import t as student_t

from f1engine.db import PROJECT_ROOT

LOGGER = logging.getLogger(__name__)
MODEL_VERSION = 2
MODEL_PATH = PROJECT_ROOT / "models" / "tyre_degradation_relative.joblib"
FUEL_BURN_RATES = (0.0, 0.015, 0.03, 0.06)
COMPOUND_ORDER = ("SOFT", "MEDIUM", "HARD")
MIN_RACE_COMPOUND_LAPS = 30
MIN_RACE_DRIVERS = 5
MIN_CIRCUIT_RACES = 3

# The compound names only state the weekend's relative order. They do not
# reveal the underlying Pirelli C1-C5 rubber selected for that event.
COMPOUND_RANK = {"SOFT": "softest", "MEDIUM": "middle", "HARD": "hardest"}

RELATIVE_TRAINING_SQL = """
    SELECT
        clean.year,
        clean.round,
        clean.event_name AS circuit,
        clean.driver_code,
        clean.team,
        clean.compound,
        clean.tyre_life,
        clean.stint_number,
        clean.lap_number,
        clean.lap_time_seconds,
        raw_lap.fresh_tyre
    FROM clean_laps AS clean
    JOIN events AS event
      ON event.season_year = clean.year
     AND event.round_number = clean.round
    JOIN sessions AS session
      ON session.event_id = event.event_id
     AND session.session_type = clean.session_type
    LEFT JOIN drivers AS driver
      ON driver.abbreviation = clean.driver_code
    LEFT JOIN laps AS raw_lap
      ON raw_lap.session_id = session.session_id
     AND raw_lap.driver_id = driver.driver_id
     AND raw_lap.lap_number = clean.lap_number
    WHERE clean.session_type = 'R'
    ORDER BY clean.year, clean.round, clean.driver_code, clean.lap_number
"""

RELATIVE_REQUIRED = (
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


def load_relative_training_data(*, engine: Any | None = None) -> pd.DataFrame:
    """Load clean race laps, including raw fresh-tyre flags for diagnostics."""
    from sqlalchemy import text

    if engine is None:
        from f1engine.db import get_engine

        active_engine = get_engine()
        owns_engine = True
    else:
        active_engine = engine
        owns_engine = False

    try:
        return pd.read_sql_query(text(RELATIVE_TRAINING_SQL), active_engine)
    finally:
        if owns_engine:
            active_engine.dispose()


def prepare_relative_target(
    raw_laps: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Create a lap-time target relative to the first three clean laps per stint.

    Laps missing fields needed to identify a stint, tyre age, compound, or
    measured time are counted and excluded from this particular model. We use
    raw lap times rather than applying a fuel-burn constant: the within-race
    race-lap fixed effects later absorb shared fuel burn and track evolution.
    """
    missing_columns = set(RELATIVE_REQUIRED).difference(raw_laps.columns)
    if missing_columns:
        raise ValueError(
            "Relative-pace input is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    data = raw_laps.copy()
    numeric_fields = ("year", "round", "tyre_life", "stint_number", "lap_number", "lap_time_seconds")
    invalid_numeric = pd.DataFrame(index=data.index)
    for field in numeric_fields:
        original = data[field].copy()
        data[field] = pd.to_numeric(data[field], errors="coerce")
        invalid_numeric[field] = original.notna() & (
            data[field].isna() | ~np.isfinite(data[field].to_numpy(dtype=float))
        )

    missing_counts = {
        field: int(data[field].isna().sum())
        for field in RELATIVE_REQUIRED
    }
    bad_numeric_counts = {
        field: int(invalid_numeric[field].sum())
        for field in numeric_fields
    }
    incomplete = data[list(RELATIVE_REQUIRED)].isna().any(axis=1)
    incomplete |= invalid_numeric.any(axis=1)
    exclusions = {
        "input_rows": len(data),
        "missing_values_by_field_total": sum(missing_counts.values()),
        "invalid_numeric_by_field": sum(bad_numeric_counts.values()),
        "rows_excluded_for_required_fields": int(incomplete.sum()),
    }
    for field, count in missing_counts.items():
        exclusions[f"missing_{field}"] = count
    for field, count in bad_numeric_counts.items():
        exclusions[f"invalid_{field}"] = count

    # Keep incomplete source rows in the database; only this explicit model
    # dataset excludes them, and the audit above reports every exclusion.
    data = data.loc[~incomplete].copy()
    data["year"] = data["year"].astype(int)
    data["round"] = data["round"].astype(int)
    data["stint_number"] = data["stint_number"].astype(int)
    data["lap_number"] = data["lap_number"].astype(int)
    data["tyre_life"] = data["tyre_life"].astype(float)
    data["lap_time_seconds"] = data["lap_time_seconds"].astype(float)
    data["race_id"] = data["year"].astype(str) + "-" + data["round"].astype(str)
    data["driver_stint_id"] = (
        data["race_id"]
        + "-"
        + data["driver_code"].astype(str)
        + "-"
        + data["stint_number"].astype(str)
    )
    data["relative_rank"] = data["compound"].map(COMPOUND_RANK)
    unknown_compounds = int(data["relative_rank"].isna().sum())
    exclusions["rows_with_unranked_compound"] = unknown_compounds
    if unknown_compounds:
        LOGGER.warning(
            "%s model rows have compound names outside SOFT/MEDIUM/HARD; "
            "they remain in the nominal analysis but cannot enter rank pooling.",
            unknown_compounds,
        )

    data = data.sort_values(
        ["year", "round", "driver_code", "stint_number", "lap_number"]
    ).reset_index(drop=True)
    group_fields = ["race_id", "driver_code", "stint_number"]
    data["stint_lap_number"] = data.groupby(group_fields, sort=False).cumcount() + 1
    data["reference_lap_count"] = data.groupby(group_fields)["lap_number"].transform(
        "size"
    ).clip(upper=3)

    # Baseline each stint on its first three usable laps, or all available
    # laps for a shorter stint. Do not silently drop short/partial stints.
    first_laps = data.groupby(group_fields, sort=False).head(3)
    reference = first_laps.groupby(group_fields).agg(
        reference_time_seconds=("lap_time_seconds", "median"),
        reference_tyre_age=("tyre_life", "median"),
        actual_reference_laps=("lap_number", "size"),
    )
    data = data.join(reference, on=group_fields)
    data["relative_time_seconds"] = (
        data["lap_time_seconds"] - data["reference_time_seconds"]
    )
    exclusions["stints_with_fewer_than_three_clean_laps"] = int(
        (reference["actual_reference_laps"] < 3).sum()
    )
    exclusions["fresh_tyre_true"] = int(data.get("fresh_tyre", pd.Series(dtype=object)).eq(True).sum())
    exclusions["fresh_tyre_false"] = int(data.get("fresh_tyre", pd.Series(dtype=object)).eq(False).sum())
    exclusions["fresh_tyre_unknown"] = int(data.get("fresh_tyre", pd.Series(index=data.index, dtype=object)).isna().sum())
    return data, exclusions


def correlation_diagnostics(data: pd.DataFrame) -> pd.DataFrame:
    """Report tyre-age correlations overall and by fresh/used tyre flag."""
    rows: list[dict[str, object]] = []
    subsets: list[tuple[str, pd.DataFrame]] = [("all", data)]
    if "fresh_tyre" in data.columns:
        for label, fresh in (("fresh", True), ("used", False)):
            subsets.append((label, data.loc[data["fresh_tyre"].eq(fresh)]))
    for label, subset in subsets:
        rows.append(
            {
                "tyre_set": label,
                "laps": len(subset),
                "tyre_life_vs_race_lap_r": subset["tyre_life"].corr(
                    subset["lap_number"]
                ),
                "tyre_life_vs_stint_lap_r": subset["tyre_life"].corr(
                    subset["stint_lap_number"]
                ),
                "fresh_flag_unknown_laps": (
                    int(subset["fresh_tyre"].isna().sum())
                    if "fresh_tyre" in subset.columns
                    else len(subset)
                ),
            }
        )
    return pd.DataFrame(rows)


def fuel_sensitivity_diagnostics(
    data: pd.DataFrame,
    rates: tuple[float, ...] = FUEL_BURN_RATES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Refit old per-race driver-adjusted slopes under four fuel assumptions."""
    summaries: list[dict[str, object]] = []
    compound_means: list[dict[str, object]] = []
    for rate in rates:
        for (race_id, circuit, compound), group in data.groupby(
            ["race_id", "circuit", "compound"], observed=True, sort=True
        ):
            if len(group) < MIN_RACE_COMPOUND_LAPS or group["driver_code"].nunique() < 3:
                continue
            diagnostic = group.copy()
            diagnostic["diagnostic_time"] = diagnostic["lap_time_seconds"] + (
                diagnostic["lap_number"] - 1
            ) * rate
            fitted = smf.ols(
                "diagnostic_time ~ tyre_life + C(driver_code)",
                data=diagnostic,
            ).fit()
            slope = float(fitted.params.get("tyre_life", np.nan))
            if not math.isfinite(slope):
                continue
            summaries.append(
                {
                    "fuel_burn_seconds_per_lap": rate,
                    "race_id": race_id,
                    "circuit": circuit,
                    "compound": compound,
                    "slope_seconds_per_lap": slope,
                    "laps": len(group),
                }
            )
        current = pd.DataFrame(
            row for row in summaries if row["fuel_burn_seconds_per_lap"] == rate
        )
        for compound, group in current.groupby("compound", observed=True, sort=True):
            compound_means.append(
                {
                    "fuel_burn_seconds_per_lap": rate,
                    "compound": compound,
                    "race_fits": len(group),
                    "mean_slope_seconds_per_lap": float(
                        group["slope_seconds_per_lap"].mean()
                    ),
                    "negative_slope_share": float(
                        group["slope_seconds_per_lap"].lt(0).mean()
                    ),
                }
            )
    return pd.DataFrame(summaries), pd.DataFrame(compound_means)


def fit_race_fixed_effects_slopes(
    data: pd.DataFrame,
    *,
    min_compound_laps: int = MIN_RACE_COMPOUND_LAPS,
    min_drivers: int = MIN_RACE_DRIVERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit race-lap and driver-stint fixed effects, logging unusable fits."""
    fitted_rows: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []
    for race_id, race in data.groupby("race_id", sort=True):
        race = race.copy()
        try:
            formula = (
                "relative_time_seconds ~ C(driver_stint_id) + C(lap_number) "
                "+ tyre_life:C(compound)"
            )
            result = smf.ols(formula, data=race).fit(
                cov_type="cluster",
                cov_kwds={"groups": race["driver_stint_id"], "use_correction": True},
            )
            rank = int(np.linalg.matrix_rank(result.model.exog))
            columns = int(result.model.exog.shape[1])
            # Statsmodels uses a generalized inverse for rank-deficient
            # designs. Keep finite slopes, but flag that some fixed effects
            # are not separately identifiable.
            design_status = "fitted"
            if rank < columns:
                design_status = f"collinear_design_{rank}_of_{columns}"
                LOGGER.warning(
                    "Race %s has a rank-deficient fixed-effects design (%s/%s); "
                    "retaining finite slope estimates and flagging the fit.",
                    race_id,
                    rank,
                    columns,
                )
            for compound, group in race.groupby("compound", observed=True, sort=True):
                term = f"tyre_life:C(compound)[{compound}]"
                if term not in result.params.index:
                    raise ValueError(f"missing coefficient {term!r}")
                slope = float(result.params[term])
                standard_error = float(result.bse[term])
                if not math.isfinite(slope) or not math.isfinite(standard_error):
                    raise ValueError(f"non-finite estimate for {compound}")
                fitted_rows.append(
                    {
                        "race_id": str(race_id),
                        "year": int(group["year"].iloc[0]),
                        "round": int(group["round"].iloc[0]),
                        "circuit": str(group["circuit"].iloc[0]),
                        "compound": str(compound),
                        "relative_rank": str(group["relative_rank"].iloc[0]),
                        "slope_seconds_per_lap": slope,
                        "standard_error": standard_error,
                        "laps": len(group),
                        "drivers": int(group["driver_code"].nunique()),
                        "stints": int(group["driver_stint_id"].nunique()),
                        "design_rank": rank,
                        "design_columns": columns,
                        "status": design_status,
                    }
                )
            status_rows.append(
                {
                    "race_id": str(race_id),
                    "status": design_status,
                    "reason": "" if design_status == "fitted" else design_status,
                    "laps": len(race),
                    "drivers": int(race["driver_code"].nunique()),
                    "stints": int(race["driver_stint_id"].nunique()),
                }
            )
        except Exception as error:
            # Keep going so one difficult or collinear race does not hide the rest.
            LOGGER.exception("Could not fit fixed-effects slopes for race %s", race_id)
            status_rows.append(
                {
                    "race_id": str(race_id),
                    "status": "failed",
                    "reason": f"{type(error).__name__}: {error}",
                    "laps": len(race),
                    "drivers": int(race["driver_code"].nunique()),
                    "stints": int(race["driver_stint_id"].nunique()),
                }
            )
    slopes = pd.DataFrame(fitted_rows)
    if not slopes.empty:
        too_small = (
            slopes["laps"].lt(min_compound_laps)
            | slopes["drivers"].lt(min_drivers)
            | slopes["standard_error"].le(0)
        )
        slopes.loc[too_small, "status"] = "too_little_data_or_unusable_se"
        slopes["plausibility_flag"] = np.where(
            slopes["slope_seconds_per_lap"].lt(-0.05)
            | slopes["slope_seconds_per_lap"].gt(0.5),
            "outside_approx_-0.05_to_0.5",
            "within_approx_range",
        )
        slopes = slopes.reset_index(drop=True)
    return slopes, pd.DataFrame(status_rows)


def random_effects_pool(
    estimates: pd.DataFrame,
    *,
    group_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Pool independent race slopes using DerSimonian-Laird random effects."""
    required = {"slope_seconds_per_lap", "standard_error"}
    if not required.issubset(estimates.columns):
        raise ValueError("Meta-analysis needs slope and standard-error columns.")
    records: list[dict[str, object]] = []
    if group_columns:
        grouped = estimates.groupby(list(group_columns), observed=True, sort=True)
    else:
        grouped = [((), estimates)]
    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = group["slope_seconds_per_lap"].to_numpy(dtype=float)
        variances = np.square(group["standard_error"].to_numpy(dtype=float))
        valid = np.isfinite(values) & np.isfinite(variances) & (variances > 0)
        values = values[valid]
        variances = variances[valid]
        if not len(values):
            continue
        fixed_weights = 1.0 / variances
        fixed_mean = float(np.sum(fixed_weights * values) / np.sum(fixed_weights))
        q_value = float(np.sum(fixed_weights * np.square(values - fixed_mean)))
        c_value = float(
            np.sum(fixed_weights)
            - np.sum(np.square(fixed_weights)) / np.sum(fixed_weights)
        )
        tau_squared = (
            max(0.0, (q_value - (len(values) - 1)) / c_value)
            if len(values) > 1 and c_value > 0
            else 0.0
        )
        random_weights = 1.0 / (variances + tau_squared)
        pooled = float(np.sum(random_weights * values) / np.sum(random_weights))
        pooled_se = float(math.sqrt(1.0 / np.sum(random_weights)))
        critical = (
            float(student_t.ppf(0.975, df=len(values) - 1))
            if len(values) > 1
            else 1.96
        )
        result: dict[str, object] = {
            "pooled_slope_seconds_per_lap": pooled,
            "standard_error": pooled_se,
            "lower_95": pooled - critical * pooled_se,
            "upper_95": pooled + critical * pooled_se,
            "race_estimates": len(values),
            "tau_squared": tau_squared,
            "negative_slope_share": float(np.mean(values < 0)),
        }
        for column, value in zip(group_columns, keys):
            result[column] = value
        records.append(result)
    return pd.DataFrame(records)


def pool_by_compound_and_circuit(slopes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create global pools and circuit pools only when at least three races exist."""
    if slopes.empty:
        return pd.DataFrame(), pd.DataFrame()
    eligible = slopes.loc[~slopes["status"].eq("too_little_data_or_unusable_se")]
    global_pools = random_effects_pool(eligible, group_columns=("compound",))
    circuit_groups = slopes.groupby(
        ["circuit", "compound"], observed=True, sort=True
    )
    enough = circuit_groups.filter(lambda group: group["race_id"].nunique() >= MIN_CIRCUIT_RACES)
    circuit_pools = random_effects_pool(
        enough.loc[~enough["status"].eq("too_little_data_or_unusable_se")],
        group_columns=("circuit", "compound"),
    )
    return global_pools, circuit_pools


def _pool_training_slopes(
    training_slopes: pd.DataFrame,
    *,
    rank_key: bool = False,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Make race-exclusive pools used by validation folds and predictions."""
    key = "relative_rank" if rank_key else "compound"
    eligible = training_slopes.loc[
        ~training_slopes["status"].eq("too_little_data_or_unusable_se")
    ]
    global_table = random_effects_pool(eligible, group_columns=(key,))
    circuit_table = random_effects_pool(
        eligible.groupby(["circuit", key], observed=True)
        .filter(lambda group: group["race_id"].nunique() >= MIN_CIRCUIT_RACES),
        group_columns=("circuit", key),
    )
    global_map = {
        str(row[key]): {
            "slope": float(row["pooled_slope_seconds_per_lap"]),
            "lower": float(row["lower_95"]),
            "upper": float(row["upper_95"]),
        }
        for _, row in global_table.iterrows()
    }
    circuit_map = {
        f"{row['circuit']}|{row[key]}": {
            "slope": float(row["pooled_slope_seconds_per_lap"]),
            "lower": float(row["lower_95"]),
            "upper": float(row["upper_95"]),
            "race_estimates": float(row["race_estimates"]),
        }
        for _, row in circuit_table.iterrows()
    }
    return global_map, circuit_map


def _old_relative_predictions(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Re-score the old pooled formula after refitting it to the relative target."""
    model = smf.ols(
        "relative_time_seconds ~ tyre_life * C(compound) + C(driver_code)",
        data=train,
    ).fit()
    prediction = test.copy()
    for column in ("compound", "driver_code"):
        categories = list(train[column].dropna().unique())
        if not categories:
            raise ValueError(f"No training data exists for {column}.")
        prediction[column] = prediction[column].where(
            prediction[column].isin(categories), categories[0]
        )
        prediction[column] = pd.Categorical(prediction[column], categories=categories)
    return np.asarray(model.predict(prediction), dtype=float)


def _relative_meta_predictions(
    train_slopes: pd.DataFrame,
    test: pd.DataFrame,
    *,
    rank_key: bool,
) -> np.ndarray:
    """Predict held-out stint-relative times from training-race wear slopes."""
    global_map, circuit_map = _pool_training_slopes(train_slopes, rank_key=rank_key)
    key_column = "relative_rank" if rank_key else "compound"
    predictions: list[float] = []
    for row in test.itertuples(index=False):
        category = getattr(row, key_column)
        estimate = circuit_map.get(f"{row.circuit}|{category}")
        if estimate is None:
            estimate = global_map.get(str(category))
        if estimate is None:
            # A compound absent from training contributes no estimated wear.
            predictions.append(0.0)
            continue
        predictions.append(
            estimate["slope"] * (float(row.tyre_life) - float(row.reference_tyre_age))
        )
    return np.asarray(predictions, dtype=float)


def evaluate_relative_models(
    data: pd.DataFrame,
    slopes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare zero, legacy-relative, nominal-pool, and rank-pool predictions."""
    data = data.reset_index(drop=True)
    race_ids = sorted(data["race_id"].unique())
    per_race_rows: list[dict[str, object]] = []
    for race_id in race_ids:
        train = data.loc[data["race_id"] != race_id]
        test = data.loc[data["race_id"] == race_id]
        train_slopes = slopes.loc[slopes["race_id"] != race_id]
        predictions = {
            "No degradation (zero)": np.zeros(len(test), dtype=float),
            "Legacy pooled linear, refit on relative target": _old_relative_predictions(
                train, test
            ),
            "New race-FE pool by nominal compound": _relative_meta_predictions(
                train_slopes, test, rank_key=False
            ),
            "New race-FE pool by relative rank": _relative_meta_predictions(
                train_slopes, test, rank_key=True
            ),
        }
        actual = test["relative_time_seconds"].to_numpy(dtype=float)
        for name, predicted in predictions.items():
            if len(predicted) != len(test) or not np.isfinite(predicted).all():
                raise ValueError(f"{name} produced invalid predictions for {race_id}.")
            per_race_rows.append(
                {
                    "race_id": race_id,
                    "year": int(test["year"].iloc[0]),
                    "round": int(test["round"].iloc[0]),
                    "circuit": str(test["circuit"].iloc[0]),
                    "model": name,
                    "mae_seconds": float(np.mean(np.abs(actual - predicted))),
                    "laps": len(test),
                }
            )

    per_race = pd.DataFrame(per_race_rows)
    race_summary = (
        per_race.groupby("model", as_index=False, sort=False)
        .agg(
            mean_race_mae_seconds=("mae_seconds", "mean"),
            standard_deviation_race_mae_seconds=("mae_seconds", "std"),
            races=("race_id", "nunique"),
        )
        .sort_values("mean_race_mae_seconds")
        .reset_index(drop=True)
    )

    train = data.loc[data["year"] < 2024]
    test = data.loc[data["year"] == 2024].copy().reset_index(drop=True)
    if train.empty or test.empty:
        raise ValueError("Chronological evaluation requires 2022-2023 train and 2024 test.")
    season_predictions = {
        "No degradation (zero)": np.zeros(len(test), dtype=float),
        "Legacy pooled linear, refit on relative target": _old_relative_predictions(
            train, test
        ),
        "New race-FE pool by nominal compound": _relative_meta_predictions(
            slopes.loc[slopes["year"] < 2024], test, rank_key=False
        ),
        "New race-FE pool by relative rank": _relative_meta_predictions(
            slopes.loc[slopes["year"] < 2024], test, rank_key=True
        ),
    }
    actual_season = test["relative_time_seconds"].to_numpy(dtype=float)
    season_rows = [
        {
            "train_years": "2022-2023",
            "test_year": 2024,
            "model": name,
            "mae_seconds": float(np.mean(np.abs(actual_season - predicted))),
            "laps": len(test),
        }
        for name, predicted in season_predictions.items()
    ]
    season_per_race = pd.DataFrame(
        [
            {
                "train_years": "2022-2023",
                "test_year": 2024,
                "race_id": race_id,
                "round": int(group["round"].iloc[0]),
                "circuit": str(group["circuit"].iloc[0]),
                "model": name,
                "mae_seconds": float(
                    np.mean(
                        np.abs(
                            group["relative_time_seconds"].to_numpy(dtype=float)
                            - season_predictions[name][group.index.to_numpy()]
                        )
                    )
                ),
                "laps": len(group),
            }
            for race_id, group in test.groupby("race_id", sort=True)
            for name in season_predictions
        ]
    )
    return race_summary, per_race, pd.DataFrame(season_rows), season_per_race


def _ordering_summary(slopes: pd.DataFrame, key: str) -> dict[str, object]:
    """Count complete per-race SOFT>MEDIUM>HARD or rank ordering checks."""
    if key == "compound":
        wanted = ("SOFT", "MEDIUM", "HARD")
    else:
        wanted = ("softest", "middle", "hardest")
    pivot = slopes.pivot_table(
        index="race_id",
        columns=key,
        values="slope_seconds_per_lap",
        aggfunc="first",
    )
    complete = pivot.dropna(subset=list(wanted))
    if complete.empty:
        return {"complete_races": 0, "ordered_races": 0, "share_ordered": 0.0}
    ordered = (
        (complete[wanted[0]] > complete[wanted[1]])
        & (complete[wanted[1]] > complete[wanted[2]])
    )
    return {
        "complete_races": len(complete),
        "ordered_races": int(ordered.sum()),
        "share_ordered": float(ordered.mean()),
    }


def fit_legacy_relative_slopes(data: pd.DataFrame) -> pd.DataFrame:
    """Fit the old pooled driver-adjusted slope formula on relative lap time."""
    rows: list[dict[str, object]] = []
    for (circuit, compound), group in data.groupby(
        ["circuit", "compound"], observed=True, sort=True
    ):
        if (
            len(group) < 100
            or group["driver_code"].nunique() < 5
            or group["tyre_life"].nunique() < 2
        ):
            continue
        fitted = smf.ols(
            "relative_time_seconds ~ tyre_life + C(driver_code)",
            data=group,
        ).fit()
        slope = float(fitted.params["tyre_life"])
        if math.isfinite(slope):
            rows.append(
                {
                    "circuit": str(circuit),
                    "compound": str(compound),
                    "slope_seconds_per_lap": slope,
                    "laps": len(group),
                }
            )
    return pd.DataFrame(rows)


def build_artifact(slopes: pd.DataFrame) -> dict[str, Any]:
    """Save pooled wear slopes with uncertainty for circuit-aware prediction."""
    nominal_global, nominal_circuit = _pool_training_slopes(slopes)
    rank_global, rank_circuit = _pool_training_slopes(slopes, rank_key=True)
    # Nominal-compound estimates are used because race-relative ranks cannot
    # distinguish the underlying C1-C5 tyre selection with this database.
    return {
        "model_version": MODEL_VERSION,
        "model_name": "Stint-relative race fixed-effects random-effects pool",
        "global": nominal_global,
        "circuits": nominal_circuit,
        "rank_global": rank_global,
        "rank_circuits": rank_circuit,
        "known_circuits": tuple(sorted(slopes["circuit"].astype(str).unique())),
        "known_compounds": tuple(sorted(slopes["compound"].astype(str).unique())),
        "training_races": tuple(sorted(slopes["race_id"].astype(str).unique())),
        "cliff_loss_threshold_seconds": 1.0,
    }


def save_artifact(slopes: pd.DataFrame, path: str | Path = MODEL_PATH) -> Path:
    """Write the fitted pool without touching the old legacy artifact."""
    import joblib

    model_path = Path(path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(build_artifact(slopes), model_path, compress=3)
    return model_path


def predict_relative_degradation(
    circuit: str,
    compound: str,
    tyre_life: int,
    *,
    model_path: str | Path = MODEL_PATH,
) -> tuple[float, float, float]:
    """Predict loss versus a fresh tyre with a point estimate and 95% interval.

    If the circuit has fewer than three race estimates for this compound, use
    the across-circuit pool and warn the caller. Any negative raw wear estimate
    remains visible in the report. The API constrains expected *loss* to zero
    or above, while the interval retains negative values when the fitted model
    supports them. Survivorship bias applies: drivers often pit before a tyre
    has fully worn out, so observed long-lived sets are a selected group.
    """
    import joblib

    if not isinstance(circuit, str) or not circuit.strip():
        raise ValueError("Circuit must be a non-empty event name.")
    if compound not in COMPOUND_ORDER:
        raise ValueError(f"Compound must be one of {COMPOUND_ORDER}.")
    if isinstance(tyre_life, bool) or not isinstance(tyre_life, (int, np.integer)):
        raise TypeError("Tyre life must be an integer lap number.")
    if tyre_life < 1:
        raise ValueError("Tyre life must be at least one lap.")
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict) or artifact.get("model_version") != MODEL_VERSION:
        raise ValueError(f"Unsupported relative degradation artifact: {model_path}")

    circuit_key = f"{circuit}|{compound}"
    estimate = artifact["circuits"].get(circuit_key)
    if estimate is None:
        estimate = artifact["global"].get(compound)
        if estimate is None:
            raise ValueError(f"No pooled estimate is available for {compound}.")
        warnings.warn(
            f"Too little circuit-specific race data for {circuit}/{compound}; "
            "using the pooled estimate across circuits.",
            RuntimeWarning,
            stacklevel=2,
        )
    age_delta = float(tyre_life - 1)
    point = max(0.0, estimate["slope"] * age_delta)
    lower = min(point, estimate["lower"] * age_delta)
    upper = max(point, estimate["upper"] * age_delta)
    if not all(math.isfinite(value) for value in (point, lower, upper)):
        raise RuntimeError("The saved degradation model returned non-finite values.")
    return point, lower, upper


def cliff_planning_lap(
    circuit: str,
    compound: str,
    *,
    loss_threshold_seconds: float = 1.0,
    max_tyre_life: int = 70,
    model_path: str | Path = MODEL_PATH,
) -> int | None:
    """Return a planning-threshold age, not a detected physical wear cliff."""
    if not math.isfinite(loss_threshold_seconds) or loss_threshold_seconds <= 0:
        raise ValueError("The planning threshold must be positive and finite.")
    if max_tyre_life < 1:
        raise ValueError("Maximum tyre life must be positive.")
    for age in range(1, max_tyre_life + 1):
        expected, _, _ = predict_relative_degradation(
            circuit,
            compound,
            age,
            model_path=model_path,
        )
        if expected >= loss_threshold_seconds:
            return age
    return None


def _markdown_table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    """Render a small Markdown table without adding an optional dependency."""
    shown = frame if columns is None else frame[columns]
    headers = [str(column) for column in shown.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in shown.itertuples(index=False, name=None):
        rendered = []
        for value in row:
            if pd.isna(value):
                rendered.append("—")
            elif isinstance(value, (float, np.floating)):
                rendered.append(f"{float(value):.4f}")
            else:
                rendered.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(rendered) + " |")
    return "\n".join(lines)


def run_analysis() -> dict[str, Any]:
    """Run diagnostics, race-level fitting, validation, and artifact saving."""
    raw_laps = load_relative_training_data()
    data, exclusions = prepare_relative_target(raw_laps)
    correlations = correlation_diagnostics(data)
    fuel_fits, fuel_summary = fuel_sensitivity_diagnostics(data)
    race_slopes, race_status = fit_race_fixed_effects_slopes(data)
    if race_slopes.empty:
        raise RuntimeError(
            "No race-compound estimates had finite slopes and standard errors; "
            "the model cannot be pooled or validated."
        )

    global_pools, circuit_pools = pool_by_compound_and_circuit(race_slopes)
    rank_pools = random_effects_pool(
        race_slopes.loc[
            ~race_slopes["status"].eq("too_little_data_or_unusable_se")
        ],
        group_columns=("relative_rank",),
    )
    race_summary, race_errors, season_summary, season_errors = (
        evaluate_relative_models(data, race_slopes)
    )
    legacy_relative_slopes = fit_legacy_relative_slopes(data)
    best_model = str(race_summary.iloc[0]["model"])
    best_race_errors = race_errors.loc[race_errors["model"].eq(best_model)].copy()
    artifact_path = save_artifact(race_slopes)

    count_fitted = int(
        (~race_slopes["status"].eq("too_little_data_or_unusable_se")).sum()
    )
    count_flagged_small = int(
        race_slopes["status"].eq("too_little_data_or_unusable_se").sum()
    )
    count_negative = int(
        race_slopes.loc[
            ~race_slopes["status"].eq("too_little_data_or_unusable_se"),
            "slope_seconds_per_lap",
        ].lt(0).sum()
    )
    count_eligible = count_fitted
    ordering_nominal = _ordering_summary(
        race_slopes.loc[
            ~race_slopes["status"].eq("too_little_data_or_unusable_se")
        ],
        "compound",
    )
    ordering_rank = _ordering_summary(
        race_slopes.loc[
            ~race_slopes["status"].eq("too_little_data_or_unusable_se")
        ],
        "relative_rank",
    )
    legacy_pivot = legacy_relative_slopes.pivot_table(
        index="circuit",
        columns="compound",
        values="slope_seconds_per_lap",
        aggfunc="first",
    )
    legacy_complete = (
        legacy_pivot.dropna(subset=["SOFT", "MEDIUM", "HARD"])
        if {"SOFT", "MEDIUM", "HARD"}.issubset(legacy_pivot.columns)
        else pd.DataFrame()
    )
    legacy_ordered = (
        int(
            (
                (legacy_complete["SOFT"] > legacy_complete["MEDIUM"])
                & (legacy_complete["MEDIUM"] > legacy_complete["HARD"])
            ).sum()
        )
        if not legacy_complete.empty
        else 0
    )
    legacy_ordering = {
        "complete_groups": len(legacy_complete),
        "ordered_groups": legacy_ordered,
        "share_ordered": (
            legacy_ordered / len(legacy_complete)
            if not legacy_complete.empty
            else 0.0
        ),
    }
    legacy_negative_share = (
        float(legacy_relative_slopes["slope_seconds_per_lap"].lt(0).mean())
        if not legacy_relative_slopes.empty
        else float("nan")
    )
    fuel_overall = fuel_fits.groupby("fuel_burn_seconds_per_lap").agg(
        mean_slope=("slope_seconds_per_lap", "mean"),
        negative_slope_share=(
            "slope_seconds_per_lap",
            lambda values: float(values.lt(0).mean()),
        ),
    )
    zero_fuel = fuel_overall.loc[0.0]
    double_fuel = fuel_overall.loc[max(FUEL_BURN_RATES)]
    collinear_races = int(
        race_status["status"].astype(str).str.startswith("collinear_design").sum()
    )
    failed_races = race_status.loc[race_status["status"].eq("failed")]
    zero_race = float(
        race_summary.loc[
            race_summary["model"].eq("No degradation (zero)"),
            "mean_race_mae_seconds",
        ].iloc[0]
    )
    zero_season = float(
        season_summary.loc[
            season_summary["model"].eq("No degradation (zero)"), "mae_seconds"
        ].iloc[0]
    )
    new_nominal_race = float(
        race_summary.loc[
            race_summary["model"].eq("New race-FE pool by nominal compound"),
            "mean_race_mae_seconds",
        ].iloc[0]
    )

    report = f"""# Tyre degradation model: relative-pace results

## What changed

Instead of predicting absolute lap time, this analysis subtracts the median of
each driver's first three clean laps in each stint from every lap in that
stint. Short stints use all available clean laps and are counted. The model
uses the measured lap time without a fuel-correction constant: race-lap-number
fixed effects absorb shared fuel burn and track evolution across the race.
Driver-stint fixed effects control for pace differences within each stint.

The fit for each race is
`relative_time ~ driver_stint_FE + race_lap_FE + tyre_life:compound`.
The resulting race/compound estimates are pooled with a DerSimonian-Laird
random-effects meta-analysis and 95% confidence intervals. A circuit-specific
pool is used only when at least {MIN_CIRCUIT_RACES} separate races contribute;
otherwise prediction falls back to the across-circuit compound estimate with
a warning.

## Data accounting and diagnostics

Input clean-view rows: **{exclusions['input_rows']:,}**. Rows excluded from this
model for missing or invalid required fields: **{exclusions['rows_excluded_for_required_fields']:,}**.
Missing required values by field: {', '.join(f"{name}={exclusions[f'missing_{name}']}" for name in RELATIVE_REQUIRED)}.
Stints with fewer than three clean baseline laps: **{exclusions['stints_with_fewer_than_three_clean_laps']:,}**;
those stints use the available first laps rather than being dropped.
Fresh-tyre flag: {exclusions['fresh_tyre_true']:,} true, {exclusions['fresh_tyre_false']:,} false,
{exclusions['fresh_tyre_unknown']:,} unknown.

Fuel-sensitivity diagnostic uses the prior per-race, driver-fixed-effect slope
fit (not the new fixed-effects model), at 0, 0.015, 0.03, and 0.06 seconds per
race lap:

{_markdown_table(fuel_summary)}

Tyre-age correlations with race lap and stint lap:

{_markdown_table(correlations)}

The clearest structural problem is the near-collinearity between tyre age and
stint lap (r={correlations.loc[correlations['tyre_set'].eq('all'), 'tyre_life_vs_stint_lap_r'].iloc[0]:.3f} overall,
{correlations.loc[correlations['tyre_set'].eq('fresh'), 'tyre_life_vs_stint_lap_r'].iloc[0]:.3f} for fresh sets, and
{correlations.loc[correlations['tyre_set'].eq('used'), 'tyre_life_vs_stint_lap_r'].iloc[0]:.3f} for used sets).
That leaves little independent information to identify wear. The assumed fuel
correction most strongly changes the old slope diagnostic: changing the rate
from 0 to {max(FUEL_BURN_RATES):.3f} seconds per race lap moves its mean slope
from {zero_fuel['mean_slope']:.4f} to {double_fuel['mean_slope']:.4f} seconds
per tyre-age lap and changes the negative-slope share from
{zero_fuel['negative_slope_share']:.1%} to {double_fuel['negative_slope_share']:.1%}.
These are sensitivities, not evidence that the larger fuel rate is correct.

## Per-race and pooled slope estimates

The range check is an explicit flag, not a filter: estimates outside the
roughly -0.05 to +0.5 seconds/lap range remain in the table. There are
{count_fitted} pool-eligible race/compound estimates, {count_flagged_small}
additional finite estimates flagged for too little data or unusable standard
error, {count_negative}/{count_eligible} ({count_negative / count_eligible:.1%})
eligible estimates below zero, {collinear_races} rank-deficient fixed-effects
race designs, and {len(failed_races)} failed races.

{_markdown_table(race_slopes, ['year','round','circuit','compound','slope_seconds_per_lap','standard_error','laps','drivers','stints','status','plausibility_flag'])}

Nominal compound random-effects pools:

{_markdown_table(global_pools, ['compound','pooled_slope_seconds_per_lap','lower_95','upper_95','race_estimates','tau_squared','negative_slope_share'])}

Circuit-specific pools (at least {MIN_CIRCUIT_RACES} races):

{_markdown_table(circuit_pools, ['circuit','compound','pooled_slope_seconds_per_lap','lower_95','upper_95','race_estimates','tau_squared']) if not circuit_pools.empty else 'No circuit/compound group had enough independent races; all predictions use global pools.'}

Relative weekend-rank pools (softest/middle/hardest):

{_markdown_table(rank_pools, ['relative_rank','pooled_slope_seconds_per_lap','lower_95','upper_95','race_estimates','tau_squared'])}

With only the labels SOFT/MEDIUM/HARD, relative-rank coding is ordered exactly
like those labels. It cannot recover which underlying Pirelli C1-C5 rubber was
used at each event. Therefore the nominal and relative-rank checks provide the
same ordering information, not an independent cure for cross-weekend compound
differences.

Compound ordering checks:

- Old approach: 3/9 complete season/circuit groups were SOFT > MEDIUM > HARD
  (33.3%).
- New nominal race fits: {ordering_nominal['ordered_races']}/{ordering_nominal['complete_races']}
  complete races ({ordering_nominal['share_ordered']:.1%}) had SOFT > MEDIUM > HARD.
- New relative-rank fits: {ordering_rank['ordered_races']}/{ordering_rank['complete_races']}
  complete races ({ordering_rank['share_ordered']:.1%}) had softest > middle > hardest.
- Prior absolute-time slopes: 25/60 were negative (41.7%); new eligible
  race-level slopes: {count_negative}/{count_eligible} ({count_negative / count_eligible:.1%}) were negative.

Before-versus-after comparison:

| approach | leave-one-race-out relative MAE (s) | negative slope share | complete-group compound ordering |
| --- | ---: | ---: | ---: |
| Original absolute-time model (before) | not measured on relative target | 25/60 (41.7%) | 3/9 (33.3%) |
| Legacy driver-adjusted formula, refit on relative target | {float(race_summary.loc[race_summary['model'].eq('Legacy pooled linear, refit on relative target'), 'mean_race_mae_seconds'].iloc[0]):.4f} | {int(legacy_relative_slopes['slope_seconds_per_lap'].lt(0).sum())}/{len(legacy_relative_slopes)} ({legacy_negative_share:.1%}) | {legacy_ordering['ordered_groups']}/{legacy_ordering['complete_groups']} ({legacy_ordering['share_ordered']:.1%}) |
| New race fixed-effects pool, nominal compounds | {new_nominal_race:.4f} | {count_negative}/{count_eligible} ({count_negative / count_eligible:.1%}) | {ordering_nominal['ordered_races']}/{ordering_nominal['complete_races']} ({ordering_nominal['share_ordered']:.1%}) |
| New race fixed-effects pool, relative rank | {float(race_summary.loc[race_summary['model'].eq('New race-FE pool by relative rank'), 'mean_race_mae_seconds'].iloc[0]):.4f} | {count_negative}/{count_eligible} ({count_negative / count_eligible:.1%}) | {ordering_rank['ordered_races']}/{ordering_rank['complete_races']} ({ordering_rank['share_ordered']:.1%}) |

The original absolute-time MAE cannot be compared directly to these relative-target scores.
The old/new ordering denominators differ because the old result grouped by
season and circuit, the relative-target legacy diagnostic groups by circuit,
and the new fixed-effects diagnostic groups by race.

## Honest validation on relative lap time

Leave-one-race-out holds out all laps from one year/round. Chronological
validation trains on 2022–2023 and tests only on 2024. The "legacy pooled
linear" comparator is refit on the same relative target using the older pooled
tyre-age/compound and driver-effect formula; this avoids comparing absolute
seconds to relative seconds.

Race-held-out MAE is the mean of per-race MAEs:

{_markdown_table(race_summary)}

Chronological 2022–2023 train / 2024 test:

{_markdown_table(season_summary)}

Per-race errors for the race-held-out winner ({best_model}):

{_markdown_table(best_race_errors, ['year','round','circuit','mae_seconds','laps'])}

"""
    report += f"""## Results and limitations

The no-degradation baseline scores {zero_race:.4f} seconds mean race MAE and
{zero_season:.4f} seconds on the 2024 season holdout. The nominal new model
scores {new_nominal_race:.4f} seconds mean race MAE. **"""
    if new_nominal_race < zero_race:
        report += "The new model beats the zero baseline on the race-held-out average"
    else:
        report += "The new model does not beat the zero baseline on the race-held-out average"
    report += f"""**, but it is not called validated unless both cross-validation
and chronological holdout show a benefit with useful uncertainty intervals.
Inspect the season-held-out table and pooled intervals before interpreting it.

This design separates common race-lap effects from within-stint tyre-age
patterns, but tyre life is still highly related to stint lap number. Driver
stint fixed effects and race-lap fixed effects can leave little independent
variation to identify wear; the rank-deficiency flags quantify this issue.
Long stints are selected by strategy and survivorship, because teams often pit
before tyres fully degrade. Compound names are relative to each weekend and
do not identify the underlying rubber. The first-three-lap baseline may
include tyres that are already used, and shorter stints have noisier
references. These are exploratory observational estimates, not causal tyre
degradation or validated strategy guidance. The prediction API clips its point
estimate to non-negative loss for planning, but its uncertainty interval keeps
negative values when supported by the fitted data.

No database schema was changed. The previous artifact is preserved in
`models/legacy/`; the new joblib artifact is
`{artifact_path.relative_to(PROJECT_ROOT).as_posix()}`.
"""
    report_path = PROJECT_ROOT / "docs" / "results_after.md"
    report_path.write_text(report, encoding="utf-8")
    (PROJECT_ROOT / "docs" / "model_results.md").write_text(report, encoding="utf-8")
    return {
        "raw_laps": raw_laps,
        "data": data,
        "exclusions": exclusions,
        "correlations": correlations,
        "fuel_fits": fuel_fits,
        "fuel_summary": fuel_summary,
        "race_slopes": race_slopes,
        "race_status": race_status,
        "global_pools": global_pools,
        "circuit_pools": circuit_pools,
        "rank_pools": rank_pools,
        "legacy_relative_slopes": legacy_relative_slopes,
        "race_summary": race_summary,
        "race_errors": race_errors,
        "season_summary": season_summary,
        "season_per_race": season_errors,
        "best_race_errors": best_race_errors,
        "artifact_path": artifact_path,
    }


def main() -> None:
    """Provide one command that can reproduce the full model and reports."""
    results = run_analysis()
    print("Relative-pace analysis complete.")
    print(f"Input clean laps: {len(results['raw_laps']):,}")
    print(
        "Rows used after explicit missing-field exclusions:",
        f"{len(results['data']):,}",
    )
    print("\nRace-held-out relative MAE:")
    print(results["race_summary"].to_string(index=False))
    print("\nChronological train 2022-2023 / test 2024:")
    print(results["season_summary"].to_string(index=False))
    print(f"\nModel artifact: {results['artifact_path']}")
    print("Reports: docs/results_after.md and docs/model_results.md")


if __name__ == "__main__":
    main()
