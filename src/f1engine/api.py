"""HTTP API for Formula 1 telemetry predictions and leaderboards."""

from typing import Any

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder

from f1engine import leaderboard, models


app = FastAPI(title="F1 Telemetry Engine")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is responsive."""
    return {"status": "ok"}


@app.get("/degradation")
def degradation(
    circuit: str,
    compound: str,
    tyre_life: int,
) -> Any:
    """Predict tyre degradation for the requested circuit and stint age."""
    result = models.predict_degradation(circuit, compound, tyre_life)
    return jsonable_encoder(result)


@app.get("/leaderboard/{year}/{round}")
def race_leaderboard(
    year: int,
    round: int,
    n: int = Query(default=5, gt=0),
) -> list[tuple[str, float]]:
    """Return the fastest laps currently stored for a race."""
    return leaderboard.top_n(year, round, n)
