# F1 Telemetry Engine

A reproducible Formula 1 data pipeline that ingests FastF1 race data into
PostgreSQL, summarizes lap telemetry, analyses tyre degradation, and serves
predictions through a small API.

## Project status

The local pipeline is implemented through the v4 tyre-degradation analysis.
The repository includes database schema and ingestion, a Redis-compatible
leaderboard, a Dockerized API, per-session Parquet exports for raw telemetry,
and an optional allowlisted export of summary tables to hosted PostgreSQL.
CI separates offline unit tests from tests requiring PostgreSQL.

## Results at a glance

The headline v4 model estimates compound-specific tyre-age slopes from
race-level fixed-effects fits, then pools independent races. It uses 60,227
usable laps from 66 race sessions with clean data; 59 eligible full-rank race
fits contribute to the headline pools. Six race designs are rank deficient,
and four races fall below the 500-clean-lap threshold.

| Compound | Degradation (seconds / tyre-age lap) | 95% interval | Race estimates |
| --- | ---: | ---: | ---: |
| HARD | 0.0507 | 0.0438 to 0.0576 | 58 |
| MEDIUM | 0.0627 | 0.0539 to 0.0714 | 58 |
| SOFT | 0.0902 | 0.0744 to 0.1060 | 51 |

Across eligible races, leave-one-race-out relative-time MAE is 1.0199 seconds
for the model versus 1.0434 for the zero-degradation baseline. The 2024
chronological holdout (train 2022-2023) is 0.8426 versus 0.9292 seconds.
These are exploratory averages, not evidence that every race improves.
Full methods, tables, exclusions, diagnostics, validation, and caveats are in
[docs/model_results.md](docs/model_results.md); the earlier v3 stint-slope
analysis remains in [docs/results_v3.md](docs/results_v3.md), and the flawed
v2 specification is preserved in [docs/results_v2_flawed.md](docs/results_v2_flawed.md).

## Architecture

```text
FastF1
  -> ingestion (Python)
  -> PostgreSQL (events, sessions, laps, stints, weather, lap summaries)
  -> clean_laps view -> v4 analysis -> model artifact and result reports
                                      -> FastAPI degradation endpoint
PostgreSQL clean laps -> Valkey leaderboard -> FastAPI leaderboard endpoint
Raw telemetry_samples -> local per-session Parquet files
PostgreSQL allowlisted summary tables -> optional hosted PostgreSQL export
```

Docker Compose provides PostgreSQL 17, Valkey 8, BetterDB Monitor, the API, and
an optional ingestion service. The API container runs as a non-root user and
only binds its published port to localhost by default.

## Quick start (Windows PowerShell)

1. Copy the example environment file only if you do not already have a local
   `.env`, then fill in the local database settings. Never commit `.env`.

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

2. Start the local services and build the API image:

   ```powershell
   docker compose up -d --build postgres valkey betterdb api
   docker compose ps
   ```

3. Activate the existing project environment and install the source package:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .
   ```

4. Open the notebooks with the `f1-telemetry` Python kernel. The v4 analysis
   requires the local PostgreSQL schema and ingested race data.

## Run the pipeline

Ingest one race, then check row counts:

```powershell
python -m f1engine.ingest 2024 1
python -m f1engine.counts
```

Ingest every round in a season after confirming the run. Existing sessions
with complete laps and lap summaries are skipped:

```powershell
python -m f1engine.ingest --season 2024
```

Generate or refresh the v4 model artifact and reports:

```powershell
python -m f1engine.tyre_model_v4
```

This writes `models/tyre_degradation_v4.joblib`,
`docs/results_v4.md`, and `docs/model_results.md`. The notebook version of
this analysis is [notebooks/04_degradation_v3.ipynb](notebooks/04_degradation_v3.ipynb).
Its filename is retained for compatibility; its content and outputs document
v4.

## API

The API is available at `http://localhost:8000` after starting the Compose
services. `GET /health` checks that the process is responsive. The degradation
endpoint returns an estimate, interval, reliability flag, scope, and warning:

```powershell
curl.exe "http://localhost:8000/degradation?circuit=Monza&compound=MEDIUM&tyre_life=10"
```

The prediction reports cross-circuit fallback when a circuit/compound pool
does not meet the minimum race count. It retains negative estimates and marks
fallback or low-confidence predictions as unreliable. The leaderboard endpoint
reads the current Valkey sorted set:

```powershell
curl.exe "http://localhost:8000/leaderboard/2024/1?n=5"
```

Populate a leaderboard from a race with:

```powershell
python -m f1engine.leaderboard 2024 1
```

The `/health` endpoint indicates API process health; it is not a full
PostgreSQL or Valkey readiness check.

## Data exports

Raw telemetry samples are opt-in during ingestion because they are much larger
than lap summaries:

```powershell
python -m f1engine.ingest 2024 1 --telemetry-samples --drivers VER,LEC
python -m f1engine.export_parquet --session-id SESSION_ID
```

Parquet files are written under `data/parquet/`, which is ignored by Git.
The read helpers support one session or all exported sessions.

The hosted PostgreSQL exporter is restricted to the core allowlist of events,
sessions, drivers, laps, stints, weather, and lap telemetry summaries. It
estimates source size and refuses to exceed its default 400 MB limit. No hosted
database is provisioned by this project; set `HOSTED_DATABASE_URL` only when a
specific destination has been chosen and is ready:

```powershell
python -m f1engine.export_hosted --max-mb 400
```

Raw `telemetry_samples` are not included in the hosted export. The current
local estimate for the allowlisted tables is approximately 35.41 MB.

## Tests and checks

The default test command runs the offline unit suite. The database integration
test is deliberately marked separately:

```powershell
python -m pytest
python -m pytest -m integration
python -m pytest -m "integration or not integration"
ruff check src tests
docker compose config --quiet
```

The GitHub Actions workflow runs the unit and PostgreSQL integration jobs
separately. The combined marker expression runs the entire suite locally;
integration tests require the configured PostgreSQL service.

## Results and limitations

The v4 estimator controls for driver, race lap, and compound intercepts within
each race, then estimates compound-specific tyre-age slopes. Only full-rank
race designs with at least 500 clean laps contribute to the headline fit.
Circuit/compound predictions require at least three eligible race estimates;
otherwise, the API falls back to the cross-circuit pool.

Fuel burn is not measured directly; the analysis uses sensitivity assumptions.
Race-lap fixed effects absorb the shared linear fuel trend, which the synthetic
fuel-mismatch experiment confirms for this model design. The cleanliness view
excludes pit-affected, wet-compound, safety/red-flag, inaccurate/deleted, and
opening laps, with overlapping reasons possible. Some circuits have few
qualifying races and wide intervals. Weekend compound labels do not identify
Pirelli's underlying C1-C5 rubber. Drivers may pit before severe fall-off,
creating survivorship bias. This is not a causal wear estimate, detected
physical cliff, or pit-strategy recommendation. See the complete
[v4 results and limitations](docs/model_results.md).

## Roadmap

- Extend validation to more seasons and track conditions as data coverage grows.
- Add race-strategy analysis with explicit stint, pit-stop, and safety-car
  uncertainty.
- Evaluate forecast calibration and decision value before presenting strategy
  recommendations.
- Add dashboard screenshots after reviewing BetterDB's live monitoring views.

## Local monitoring

BetterDB Monitor is available at [http://localhost:3001](http://localhost:3001).
Generate activity with `python -m f1engine.bench_cache` and the leaderboard
command. The current in-memory monitor storage does not support every key
analytics metric; some dashboard metrics may therefore be unavailable.
