"""Helpers for preparing data used by the tyre degradation models."""

import math
import warnings
from pathlib import Path
from typing import TypeAlias

import numpy as np
import pandas as pd
import joblib
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import Engine, text
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.regression.mixed_linear_model import MixedLMResultsWrapper

from f1engine.db import PROJECT_ROOT, get_engine


# This is an estimate, matching the illustrative value used by the SQL query.
DEFAULT_FUEL_BURN_SECONDS_PER_LAP = 0.03

_TRAINING_DATA_SQL = text(
    """
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
        weather_summary.track_temperature_c,
        clean.lap_time_seconds
            + (clean.lap_number - 1)
                * CAST(:fuel_burn_seconds_per_lap AS double precision)
            AS fuel_corrected_lap_time_seconds
    FROM clean_laps AS clean
    JOIN events AS event
      ON event.season_year = clean.year
     AND event.round_number = clean.round
    JOIN sessions AS session
      ON session.event_id = event.event_id
     AND session.session_type = clean.session_type
    LEFT JOIN (
        SELECT session_id, AVG(track_temp) AS track_temperature_c
        FROM weather
        GROUP BY session_id
    ) AS weather_summary
      ON weather_summary.session_id = session.session_id
    WHERE clean.session_type = 'R'
    ORDER BY clean.year, clean.round, clean.driver_code, clean.lap_number
    """
)

MODEL_MIN_LAPS = 100
MODEL_MIN_DRIVERS = 5
DEFAULT_DEGRADATION_MODEL_PATH = (
    PROJECT_ROOT / "models" / "tyre_degradation_v3.joblib"
)
LEGACY_DEGRADATION_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "legacy"
    / "tyre_degradation_mixedlm_exploratory.joblib"
)
DEFAULT_CLIFF_LOSS_THRESHOLD_SECONDS = 1.0
DEGRADATION_MODEL_VERSION = 1

LinearBaselineKey: TypeAlias = tuple[str, str]


def load_training_data(
    estimated_fuel_burn_seconds_per_lap: float = DEFAULT_FUEL_BURN_SECONDS_PER_LAP,
    *,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Load clean race laps with estimated starting-fuel-corrected lap times.

    The correction adds the estimated fuel-burn penalty back to each lap:
    ``lap_time + (lap_number - 1) * estimated_fuel_burn_seconds_per_lap``.
    The default 0.03 seconds per lap is an illustrative estimate, not a
    measured constant. Rows with missing tyre ages or compounds are retained
    so callers can inspect and report those exclusions before modeling.
    """
    if not math.isfinite(estimated_fuel_burn_seconds_per_lap):
        raise ValueError("The estimated fuel-burn rate must be a finite number.")
    if estimated_fuel_burn_seconds_per_lap < 0:
        raise ValueError("The estimated fuel-burn rate cannot be negative.")

    owns_engine = engine is None
    active_engine = engine or get_engine()
    try:
        return pd.read_sql_query(
            _TRAINING_DATA_SQL,
            active_engine,
            params={
                "fuel_burn_seconds_per_lap": estimated_fuel_burn_seconds_per_lap
            },
        )
    finally:
        if owns_engine:
            active_engine.dispose()


def fit_linear_baselines(
    training_data: pd.DataFrame,
    *,
    min_laps: int = MODEL_MIN_LAPS,
    min_drivers: int = MODEL_MIN_DRIVERS,
) -> tuple[pd.DataFrame, dict[LinearBaselineKey, RegressionResultsWrapper]]:
    """Fit tyre-age slopes per circuit and compound with driver fixed effects.

    The driver indicators compare each driver's laps against that driver's
    own average pace, helping driver pace differences from biasing the tyre-age
    slope. Groups below the minimum lap or driver counts are included in the
    returned table with a status but are not fitted.

    A fit based on one race is descriptive for that race only; it does not
    show that the slope generalizes to other races at the same circuit.
    """
    if min_laps < 1 or min_drivers < 1:
        raise ValueError("Minimum lap and driver counts must both be positive.")

    required_columns = {
        "circuit",
        "compound",
        "driver_code",
        "year",
        "round",
        "tyre_life",
        "fuel_corrected_lap_time_seconds",
    }
    missing_columns = required_columns.difference(training_data.columns)
    if missing_columns:
        raise ValueError(
            "Training data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    required_order = [
        "circuit",
        "compound",
        "driver_code",
        "year",
        "round",
        "tyre_life",
        "fuel_corrected_lap_time_seconds",
    ]
    model_data = training_data[required_order].copy()
    null_counts = model_data[required_order].isna().sum()
    missing_values = null_counts[null_counts > 0]
    if not missing_values.empty:
        details = ", ".join(
            f"{column}={count}" for column, count in missing_values.items()
        )
        raise ValueError(
            "Cannot fit baseline models with missing required values: " + details
        )

    for column in ("tyre_life", "fuel_corrected_lap_time_seconds"):
        model_data[column] = pd.to_numeric(model_data[column], errors="raise")
        if not model_data[column].map(math.isfinite).all():
            raise ValueError(f"Training column {column} contains non-finite values.")

    model_data["race_id"] = (
        model_data["year"].astype(str) + "-" + model_data["round"].astype(str)
    )
    grouped = model_data.groupby(["circuit", "compound"], observed=True, sort=True)
    rows: list[dict[str, object]] = []
    fitted_models: dict[LinearBaselineKey, RegressionResultsWrapper] = {}

    for (circuit, compound), group in grouped:
        lap_count = len(group)
        driver_count = group["driver_code"].nunique()
        race_count = group["race_id"].nunique()
        status = "Fitted; one race only, descriptive" if race_count < 2 else "Fitted"
        slope: float | None = None
        r_squared: float | None = None

        if lap_count < min_laps or driver_count < min_drivers:
            status = "Too little data"
        elif group["tyre_life"].nunique() < 2:
            status = "Not fitted; tyre age does not vary"
        else:
            fitted = smf.ols(
                "fuel_corrected_lap_time_seconds ~ tyre_life + C(driver_code)",
                data=group,
            ).fit()
            slope = float(fitted.params["tyre_life"])
            r_squared = float(fitted.rsquared)
            fitted_models[(str(circuit), str(compound))] = fitted

        rows.append(
            {
                "circuit": circuit,
                "compound": compound,
                "slope_seconds_per_lap": slope,
                "number_of_laps": lap_count,
                "r_squared": r_squared,
                "number_of_drivers": driver_count,
                "number_of_races": race_count,
                "status": status,
            }
        )

    return pd.DataFrame(rows), fitted_models


def fit_naive_baseline(training_data: pd.DataFrame) -> pd.DataFrame:
    """Build the naive predictor: mean lap time per circuit and compound.

    Call this using only the training portion of a validation fold to avoid
    letting held-out race lap times leak into their own predictions.
    """
    required_columns = {
        "circuit",
        "compound",
        "fuel_corrected_lap_time_seconds",
    }
    missing_columns = required_columns.difference(training_data.columns)
    if missing_columns:
        raise ValueError(
            "Training data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    required_order = [
        "circuit",
        "compound",
        "fuel_corrected_lap_time_seconds",
    ]
    model_data = training_data[required_order].copy()
    null_counts = model_data[required_order].isna().sum()
    missing_values = null_counts[null_counts > 0]
    if not missing_values.empty:
        details = ", ".join(
            f"{column}={count}" for column, count in missing_values.items()
        )
        raise ValueError(
            "Cannot fit the naive baseline with missing required values: " + details
        )

    model_data["fuel_corrected_lap_time_seconds"] = pd.to_numeric(
        model_data["fuel_corrected_lap_time_seconds"], errors="raise"
    )
    if not model_data["fuel_corrected_lap_time_seconds"].map(math.isfinite).all():
        raise ValueError("Lap times contain non-finite values.")

    return (
        model_data.groupby(["circuit", "compound"], observed=True, sort=True)
        .agg(
            naive_mean_lap_time_seconds=(
                "fuel_corrected_lap_time_seconds",
                "mean",
            ),
            number_of_laps=("fuel_corrected_lap_time_seconds", "size"),
        )
        .reset_index()
    )


_CV_REQUIRED_COLUMNS = {
    "year",
    "round",
    "circuit",
    "driver_code",
    "compound",
    "tyre_life",
    "lap_number",
    "fuel_corrected_lap_time_seconds",
}


def _validate_cv_data(training_data: pd.DataFrame) -> pd.DataFrame:
    """Validate labels and identifiers without silently dropping any laps."""
    missing_columns = _CV_REQUIRED_COLUMNS.difference(training_data.columns)
    if missing_columns:
        raise ValueError(
            "Cross-validation data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    data = training_data.copy()
    required_order = sorted(_CV_REQUIRED_COLUMNS)
    missing_values = data[required_order].isna().sum()
    missing_values = missing_values[missing_values > 0]
    if not missing_values.empty:
        details = ", ".join(
            f"{column}={count}" for column, count in missing_values.items()
        )
        raise ValueError(
            "Cross-validation requires complete labels and race identifiers: "
            + details
        )

    numeric_columns = [
        "year",
        "round",
        "tyre_life",
        "lap_number",
        "fuel_corrected_lap_time_seconds",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="raise")
        if not np.isfinite(data[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Cross-validation column {column} has non-finite values.")

    data["race_id"] = (
        data["year"].astype(int).astype(str)
        + "-"
        + data["round"].astype(int).astype(str)
    )
    return data


def _race_fold_linear_predictions(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> np.ndarray:
    """Predict with a pooled, driver-fixed-effects linear model.

    This pooled model is used for race-held-out evaluation because the
    per-circuit fits from Stage 2 have no training laps for a held-out circuit.
    """
    formula = (
        "fuel_corrected_lap_time_seconds "
        "~ tyre_life * C(compound) + C(driver_code)"
    )
    model = smf.ols(formula, data=train).fit()

    prediction_data = test.copy()
    for column in ("compound", "driver_code"):
        known_values = list(train[column].dropna().unique())
        if not known_values:
            raise ValueError(f"No training values are available for {column}.")
        fallback = known_values[0]
        prediction_data[column] = prediction_data[column].where(
            prediction_data[column].isin(known_values),
            fallback,
        )
        prediction_data[column] = pd.Categorical(
            prediction_data[column],
            categories=known_values,
        )

    return np.asarray(model.predict(prediction_data), dtype=float)


def _race_fold_mixed_effects_predictions(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    max_iterations: int,
    race_id: str,
) -> tuple[np.ndarray, dict[str, object]]:
    """Fit random driver intercepts and add only training-derived effects."""
    formula = "fuel_corrected_lap_time_seconds ~ tyre_life * C(compound)"
    model = smf.mixedlm(formula, data=train, groups=train["driver_code"])
    fitted: MixedLMResultsWrapper = model.fit(
        reml=False,
        method="powell",
        maxiter=max_iterations,
        disp=False,
    )

    prediction_data = test.copy()
    known_compounds = list(train["compound"].dropna().unique())
    if not known_compounds:
        raise ValueError("No training values are available for compound.")
    prediction_data["compound"] = prediction_data["compound"].where(
        prediction_data["compound"].isin(known_compounds),
        known_compounds[0],
    )
    prediction_data["compound"] = pd.Categorical(
        prediction_data["compound"],
        categories=known_compounds,
    )

    predictions = np.asarray(fitted.predict(prediction_data), dtype=float)
    random_intercept_variance = float(fitted.cov_re.iloc[0, 0])
    used_driver_effects = False

    # A zero variance estimate means the fold found no stable driver offset.
    # Statsmodels cannot calculate conditional effects from a singular matrix,
    # so use the valid population-level prediction and make that explicit.
    if random_intercept_variance > 1e-10:
        random_intercepts = {
            str(driver): float(effect.iloc[0])
            for driver, effect in fitted.random_effects.items()
        }
        predictions += (
            prediction_data["driver_code"]
            .map(random_intercepts)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        used_driver_effects = True
    else:
        warnings.warn(
            f"MixedLM estimated near-zero driver variance for held-out race "
            f"{race_id}; using population-level predictions for that fold.",
            RuntimeWarning,
            stacklevel=2,
        )

    if not fitted.converged:
        warnings.warn(
            f"MixedLM did not converge for held-out race {race_id}.",
            RuntimeWarning,
            stacklevel=2,
        )

    return predictions, {
        "converged": bool(fitted.converged),
        "random_intercept_variance": random_intercept_variance,
        "used_driver_effects": used_driver_effects,
    }


def _fit_race_fold_gradient_boosting(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    max_iterations: int,
) -> np.ndarray:
    """Train a gradient-boosted model with fold-fitted preprocessing."""
    categorical_features = ["compound", "circuit", "team"]
    numeric_features = ["tyre_life", "lap_number", "track_temperature_c"]
    available_categorical = [
        column for column in categorical_features if column in train.columns
    ]
    available_numeric = [column for column in numeric_features if column in train.columns]
    if not available_numeric:
        raise ValueError("No numeric features are available for gradient boosting.")

    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if available_categorical:
        categorical_pipeline = Pipeline(
            [
                (
                    "imputer",
                    SimpleImputer(strategy="most_frequent"),
                ),
                (
                    "one_hot",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ),
            ]
        )
        transformers.append(
            ("categorical", categorical_pipeline, available_categorical)
        )
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ]
    )
    transformers.append(("numeric", numeric_pipeline, available_numeric))

    preprocessing = ColumnTransformer(
        transformers,
        sparse_threshold=0.0,
    )
    estimator = Pipeline(
        [
            ("preprocessing", preprocessing),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    max_iter=max_iterations,
                    max_leaf_nodes=15,
                    l2_regularization=1.0,
                    early_stopping=True,
                    random_state=42,
                ),
            ),
        ]
    )
    estimator.fit(
        train[available_categorical + available_numeric],
        train["fuel_corrected_lap_time_seconds"],
    )
    return np.asarray(
        estimator.predict(test[available_categorical + available_numeric]),
        dtype=float,
    )


def evaluate_models_leave_one_race_out(
    training_data: pd.DataFrame,
    *,
    mixed_max_iterations: int = 100,
    gradient_boosting_iterations: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare four models using Leave-One-Race-Out cross-validation.

    A circuit/compound mean is available when that group appeared in another
    training race. For an unseen group, the naive model explicitly falls back
    to the training-fold mean for that compound, then to the overall training
    mean if that compound is absent. The linear comparison is pooled
    (compound-specific tyre-age slopes plus driver fixed effects), since the
    Stage 2 per-circuit models cannot be trained for an unseen circuit.

    Weather temperature, when present, is the session's average track
    temperature. Missing feature values are imputed inside each training fold.
    The label, tyre age, lap number, and race identifiers are never dropped.

    Returns a model-level table ranked by mean per-race MAE and one row per
    race/model for the per-race error report.
    """
    if mixed_max_iterations < 1 or gradient_boosting_iterations < 1:
        raise ValueError("Model iteration limits must be positive.")
    data = _validate_cv_data(training_data)
    if data["race_id"].nunique() < 2:
        raise ValueError("Leave-one-race-out evaluation requires at least two races.")

    splitter = LeaveOneGroupOut()
    grouped_errors: dict[str, list[dict[str, object]]] = {
        "Naive circuit/compound mean": [],
        "Pooled driver-fixed-effects linear": [],
        "Driver random-intercept MixedLM": [],
        "HistGradientBoostingRegressor": [],
    }

    for train_indices, test_indices in splitter.split(
        data,
        groups=data["race_id"],
    ):
        train = data.iloc[train_indices].copy()
        test = data.iloc[test_indices].copy()
        training_mean = float(train["fuel_corrected_lap_time_seconds"].mean())
        compound_means = train.groupby(
            "compound", observed=True
        )["fuel_corrected_lap_time_seconds"].mean()
        circuit_compound_means = train.groupby(
            ["circuit", "compound"], observed=True
        )["fuel_corrected_lap_time_seconds"].mean()

        naive_predictions = np.array(
            [
                circuit_compound_means.get(
                    (row.circuit, row.compound),
                    compound_means.get(row.compound, training_mean),
                )
                for row in test[["circuit", "compound"]].itertuples(index=False)
            ],
            dtype=float,
        )
        race_id = str(test["race_id"].iloc[0])
        mixed_predictions, mixed_diagnostics = _race_fold_mixed_effects_predictions(
            train,
            test,
            max_iterations=mixed_max_iterations,
            race_id=race_id,
        )
        predictions_by_model = {
            "Naive circuit/compound mean": naive_predictions,
            "Pooled driver-fixed-effects linear": _race_fold_linear_predictions(
                train,
                test,
            ),
            "Driver random-intercept MixedLM": mixed_predictions,
            "HistGradientBoostingRegressor": _fit_race_fold_gradient_boosting(
                train,
                test,
                max_iterations=gradient_boosting_iterations,
            ),
        }

        actual = test["fuel_corrected_lap_time_seconds"].to_numpy(dtype=float)
        for model_name, predictions in predictions_by_model.items():
            if len(predictions) != len(test) or not np.isfinite(predictions).all():
                raise ValueError(
                    f"{model_name} produced invalid predictions for race {race_id}."
                )
            group_fallbacks = sum(
                (row.circuit, row.compound) not in circuit_compound_means.index
                for row in test[["circuit", "compound"]].itertuples(index=False)
            )
            grouped_errors[model_name].append(
                {
                    "year": int(test["year"].iloc[0]),
                    "round": int(test["round"].iloc[0]),
                    "race_id": race_id,
                    "circuit": str(test["circuit"].iloc[0]),
                    "model": model_name,
                    "mae_seconds": float(np.mean(np.abs(actual - predictions))),
                    "number_of_laps": len(test),
                    "naive_group_fallback_pct": (
                        100.0 * group_fallbacks / len(test)
                        if model_name == "Naive circuit/compound mean"
                        else np.nan
                    ),
                    "mixedlm_converged": (
                        mixed_diagnostics["converged"]
                        if model_name == "Driver random-intercept MixedLM"
                        else None
                    ),
                    "mixedlm_random_intercept_variance": (
                        mixed_diagnostics["random_intercept_variance"]
                        if model_name == "Driver random-intercept MixedLM"
                        else np.nan
                    ),
                    "mixedlm_used_driver_effects": (
                        mixed_diagnostics["used_driver_effects"]
                        if model_name == "Driver random-intercept MixedLM"
                        else None
                    ),
                }
            )

    per_race = pd.DataFrame(
        row for model_rows in grouped_errors.values() for row in model_rows
    )
    summary = (
        per_race.groupby("model", as_index=False, sort=False)
        .agg(
            mean_race_mae_seconds=("mae_seconds", "mean"),
            standard_deviation_race_mae_seconds=("mae_seconds", "std"),
            number_of_races=("race_id", "nunique"),
        )
        .sort_values("mean_race_mae_seconds")
        .reset_index(drop=True)
    )
    summary["rank"] = np.arange(1, len(summary) + 1)
    naive_fallbacks = per_race[
        per_race["model"] == "Naive circuit/compound mean"
    ]["naive_group_fallback_pct"]
    summary["naive_group_fallback_pct"] = np.nan
    summary.loc[summary["model"] == "Naive circuit/compound mean", "naive_group_fallback_pct"] = (
        float(naive_fallbacks.mean())
    )
    mixed_diagnostics = per_race[
        per_race["model"] == "Driver random-intercept MixedLM"
    ]
    summary["mixedlm_converged_folds"] = np.nan
    summary["mixedlm_driver_effect_folds"] = np.nan
    mixed_mask = summary["model"] == "Driver random-intercept MixedLM"
    summary.loc[mixed_mask, "mixedlm_converged_folds"] = int(
        mixed_diagnostics["mixedlm_converged"].sum()
    )
    summary.loc[mixed_mask, "mixedlm_driver_effect_folds"] = int(
        mixed_diagnostics["mixedlm_used_driver_effects"].sum()
    )
    return summary, per_race.sort_values(["race_id", "model"]).reset_index(drop=True)


def evaluate_models_held_out_seasons(
    training_data: pd.DataFrame,
    *,
    mixed_max_iterations: int = 100,
    gradient_boosting_iterations: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate models on each season using only earlier seasons for training.

    The first season is training-only because there is no earlier data to train
    on. This chronological split measures whether past seasons can predict a
    future season, rather than allowing future races to inform the model.
    """
    if mixed_max_iterations < 1 or gradient_boosting_iterations < 1:
        raise ValueError("Model iteration limits must be positive.")
    data = _validate_cv_data(training_data)
    seasons = sorted(data["year"].unique())
    if len(seasons) < 2:
        raise ValueError(
            "Held-out-season evaluation requires at least two seasons."
        )

    rows: list[dict[str, object]] = []
    model_names = (
        "Naive circuit/compound mean",
        "Pooled driver-fixed-effects linear",
        "Driver random-intercept MixedLM",
        "HistGradientBoostingRegressor",
    )
    for held_out_year in seasons[1:]:
        train = data[data["year"] < held_out_year].copy()
        test = data[data["year"] == held_out_year].copy()
        if train.empty or test.empty:
            raise ValueError(
                f"Season {held_out_year} does not have both training and test laps."
            )

        training_mean = float(train["fuel_corrected_lap_time_seconds"].mean())
        compound_means = train.groupby(
            "compound", observed=True
        )["fuel_corrected_lap_time_seconds"].mean()
        circuit_compound_means = train.groupby(
            ["circuit", "compound"], observed=True
        )["fuel_corrected_lap_time_seconds"].mean()
        naive_predictions = np.array(
            [
                circuit_compound_means.get(
                    (row.circuit, row.compound),
                    compound_means.get(row.compound, training_mean),
                )
                for row in test[["circuit", "compound"]].itertuples(index=False)
            ],
            dtype=float,
        )
        mixed_predictions, mixed_diagnostics = _race_fold_mixed_effects_predictions(
            train,
            test,
            max_iterations=mixed_max_iterations,
            race_id=f"season {held_out_year}",
        )
        predictions_by_model = {
            model_names[0]: naive_predictions,
            model_names[1]: _race_fold_linear_predictions(train, test),
            model_names[2]: mixed_predictions,
            model_names[3]: _fit_race_fold_gradient_boosting(
                train,
                test,
                max_iterations=gradient_boosting_iterations,
            ),
        }
        actual = test["fuel_corrected_lap_time_seconds"].to_numpy(dtype=float)
        group_fallbacks = sum(
            (row.circuit, row.compound) not in circuit_compound_means.index
            for row in test[["circuit", "compound"]].itertuples(index=False)
        )

        for model_name, predictions in predictions_by_model.items():
            if len(predictions) != len(test) or not np.isfinite(predictions).all():
                raise ValueError(
                    f"{model_name} produced invalid predictions for season "
                    f"{held_out_year}."
                )
            rows.append(
                {
                    "held_out_year": int(held_out_year),
                    "model": model_name,
                    "mae_seconds": float(np.mean(np.abs(actual - predictions))),
                    "number_of_laps": len(test),
                    "naive_group_fallback_pct": (
                        100.0 * group_fallbacks / len(test)
                        if model_name == model_names[0]
                        else np.nan
                    ),
                    "mixedlm_converged": (
                        mixed_diagnostics["converged"]
                        if model_name == model_names[2]
                        else None
                    ),
                    "mixedlm_used_driver_effects": (
                        mixed_diagnostics["used_driver_effects"]
                        if model_name == model_names[2]
                        else None
                    ),
                }
            )

    per_season = pd.DataFrame(rows)
    summary = (
        per_season.groupby("model", as_index=False, sort=False)
        .agg(
            mean_season_mae_seconds=("mae_seconds", "mean"),
            number_of_seasons=("held_out_year", "nunique"),
        )
        .sort_values("mean_season_mae_seconds")
        .reset_index(drop=True)
    )
    summary["rank"] = np.arange(1, len(summary) + 1)
    return summary, per_season.sort_values(
        ["held_out_year", "model"]
    ).reset_index(drop=True)


def _validate_degradation_training_data(training_data: pd.DataFrame) -> pd.DataFrame:
    """Keep model fitting explicit about missing and invalid training rows."""
    required_columns = [
        "circuit",
        "compound",
        "driver_code",
        "tyre_life",
        "fuel_corrected_lap_time_seconds",
    ]
    missing_columns = set(required_columns).difference(training_data.columns)
    if missing_columns:
        raise ValueError(
            "Final model data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    data = training_data[required_columns].copy()
    missing_values = data[required_columns].isna().sum()
    missing_values = missing_values[missing_values > 0]
    if not missing_values.empty:
        details = ", ".join(
            f"{column}={count}" for column, count in missing_values.items()
        )
        raise ValueError(
            "Final model requires complete values; no rows were silently dropped: "
            + details
        )

    for column in ("tyre_life", "fuel_corrected_lap_time_seconds"):
        data[column] = pd.to_numeric(data[column], errors="raise")
        if not np.isfinite(data[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Final model column {column} has non-finite values.")
    if (data["tyre_life"] < 1).any():
        raise ValueError("Tyre life must be at least one lap.")
    return data


def fit_final_degradation_model(
    training_data: pd.DataFrame,
    *,
    max_iterations: int = 500,
) -> dict[str, object]:
    """Fit an interpretable mixed-effects wear model on supplied training laps.

    The model has circuit intercepts, compound-specific linear tyre-age
    effects, and a random intercept for driver. Its time-loss prediction
    subtracts the age-one prediction from the requested age, so both the
    circuit intercept and driver effect cancel. Consequently this version
    returns the same wear rate for a given compound at every known circuit;
    circuit is accepted and validated to prevent unsupported circuit requests.
    This helper fits the model but does not choose it over other CV candidates.
    """
    if max_iterations < 1:
        raise ValueError("The MixedLM iteration limit must be positive.")
    data = _validate_degradation_training_data(training_data)
    if data["driver_code"].nunique() < 2:
        raise ValueError("The mixed-effects model needs at least two drivers.")
    if data["circuit"].nunique() < 2:
        raise ValueError("The mixed-effects model needs at least two circuits.")
    if data["compound"].nunique() < 2:
        raise ValueError("The mixed-effects model needs at least two compounds.")

    fitted: MixedLMResultsWrapper = smf.mixedlm(
        "fuel_corrected_lap_time_seconds "
        "~ C(circuit) + tyre_life * C(compound)",
        data=data,
        groups=data["driver_code"],
    ).fit(
        reml=False,
        method="powell",
        maxiter=max_iterations,
        disp=False,
    )
    if not fitted.converged:
        raise RuntimeError(
            "The final MixedLM did not converge; refusing to save an unverified model."
        )

    return {
        "model_version": DEGRADATION_MODEL_VERSION,
        "model_name": "Driver random-intercept MixedLM",
        "model": fitted,
        "circuits": tuple(sorted(data["circuit"].astype(str).unique())),
        "compounds": tuple(sorted(data["compound"].astype(str).unique())),
        "max_observed_tyre_life": {
            str(compound): int(group["tyre_life"].max())
            for compound, group in data.groupby("compound", observed=True)
        },
        "training_rows": len(data),
        "training_drivers": data["driver_code"].nunique(),
        "training_years": tuple(
            sorted(training_data["year"].dropna().astype(int).unique())
        )
        if "year" in training_data
        else (),
        "fuel_burn_seconds_per_lap": DEFAULT_FUEL_BURN_SECONDS_PER_LAP,
        "cliff_loss_threshold_seconds": DEFAULT_CLIFF_LOSS_THRESHOLD_SECONDS,
    }


def save_degradation_model(
    training_data: pd.DataFrame | None = None,
    *,
    path: str | Path = DEFAULT_DEGRADATION_MODEL_PATH,
    max_iterations: int = 500,
) -> Path:
    """Fit primary per-stint slopes and save their race-bootstrap artifact."""
    from f1engine.tyre_model_v3 import (
        DEFAULT_FUEL_EFFECT_S_PER_KG,
        build_artifact,
        fit_stint_slopes,
        load_laps,
        prepare_laps,
    )

    raw_laps = load_laps() if training_data is None else training_data
    clean_laps, _ = prepare_laps(raw_laps)
    slopes, _ = fit_stint_slopes(clean_laps, DEFAULT_FUEL_EFFECT_S_PER_KG)
    max_age = (
        clean_laps.groupby("compound", observed=True)["tyre_life"]
        .max()
        .astype(int)
        .to_dict()
    )
    artifact = build_artifact(
        slopes,
        max_tyre_age_by_compound={str(key): int(value) for key, value in max_age.items()},
    )
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, artifact_path, compress=3)
    return artifact_path


def predict_degradation(
    circuit: str,
    compound: str,
    tyre_life: int,
    *,
    model_path: str | Path = DEFAULT_DEGRADATION_MODEL_PATH,
) -> tuple[float, float, float, bool]:
    """Return expected loss, 95% bounds, and a reliability flag.

    Circuit-specific pooling is used only when at least three races support it;
    otherwise this API warns and falls back to the cross-circuit pool. Negative
    estimates are not clamped. Reliability is false if the interval includes
    zero or if a fallback is used. Survivorship bias applies because drivers
    often pit before tyres fall off.
    """
    from f1engine.tyre_model_v3 import predict_relative_degradation

    return predict_relative_degradation(
        circuit,
        compound,
        tyre_life,
        model_path=model_path,
    )


def cliff_lap(
    circuit: str,
    compound: str,
    *,
    loss_threshold_seconds: float = DEFAULT_CLIFF_LOSS_THRESHOLD_SECONDS,
    model_path: str | Path = DEFAULT_DEGRADATION_MODEL_PATH,
) -> int | None:
    """Return a planning threshold, not a detected physical degradation cliff.

    Drivers often pit before tyres fall off, creating survivorship bias in
    observed old tyres. This linear planning estimate is not a physical
    change-point detector.
    """
    from f1engine.tyre_model_v3 import cliff_planning_lap

    return cliff_planning_lap(
        circuit,
        compound,
        loss_threshold_seconds=loss_threshold_seconds,
        model_path=model_path,
    )
