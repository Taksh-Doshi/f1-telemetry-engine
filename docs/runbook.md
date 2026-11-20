# Local runbook

This runbook uses Windows PowerShell and the repository's existing `.venv`.
Keep `.env` local; do not replace it if it already contains working settings.

## 1. Start the local stack

If `.env` does not exist, create it from the example and fill in the local
PostgreSQL password and ports:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Start PostgreSQL, Valkey, the monitor, and the API:

```powershell
docker compose up -d --build postgres valkey betterdb api
docker compose ps
```

Expected services are `postgres`, `valkey`, `betterdb`, and `api`; PostgreSQL
and Valkey should report healthy. The monitor is bound to
`http://localhost:3001`, and the API is bound to `http://localhost:8000`.

Activate the project environment and install the project if needed:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 2. Ingest and analyze

Ingest one race session, then inspect the database row counts:

```powershell
python -m f1engine.ingest 2024 1
python -m f1engine.counts
```

Raw telemetry is opt-in. The race and lap data should already exist before
requesting samples:

```powershell
python -m f1engine.ingest 2024 1 --telemetry-samples --drivers VER,LEC
python -m f1engine.export_parquet --session-id SESSION_ID
```

Run the v4 pipeline to refresh the model and reports:

```powershell
python -m f1engine.tyre_model_v4
```

The current local run reports 60,706 source rows, 60,227 usable model rows,
66 race sessions with clean data, and 59 eligible full-rank estimates. Six
race designs are rank deficient; four races are below the 500-clean-lap
threshold.

The cross-circuit results currently written to
[`model_results.md`](./model_results.md) are:

| Compound | Slope (seconds per tyre-age lap) | 95% interval | Race estimates |
| --- | ---: | ---: | ---: |
| HARD | 0.0507 | 0.0438 to 0.0576 | 58 |
| MEDIUM | 0.0627 | 0.0539 to 0.0714 | 58 |
| SOFT | 0.0902 | 0.0744 to 0.1060 | 51 |

The report includes the low-data and rank-deficient races, circuit pools,
fuel-assumption/mismatch sensitivity, synthetic recovery, and both
leave-one-race-out and chronological held-out evaluations. These are
exploratory associations, not causal wear rates or strategy recommendations.

## 3. Check the API and leaderboard

The health endpoint verifies that the API process is responsive:

```powershell
curl.exe http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Query the degradation estimate and its reliability metadata:

```powershell
curl.exe "http://localhost:8000/degradation?circuit=Monza&compound=MEDIUM&tyre_life=10"
```

The JSON response includes `expected_loss_per_lap`, `lower_95`, `upper_95`,
`reliable`, `scope`, and `warning`. A circuit/compound pool without enough
independent races falls back to the cross-circuit pool and is flagged.
For the current artifact, the example request returns:

```json
{
  "expected_loss_per_lap": 0.06265284681103321,
  "lower_95": 0.053904793073149146,
  "upper_95": 0.07140090054891728,
  "reliable": false,
  "scope": "cross-circuit",
  "warning": "Monza is flagged low_data or has fewer than 3 eligible race estimates; using the cross-circuit pool."
}
```

Populate and query a race leaderboard:

```powershell
python -m f1engine.leaderboard 2024 1
curl.exe "http://localhost:8000/leaderboard/2024/1?n=5"
```

On the current local dataset, the leaderboard endpoint returns the five
fastest stored laps in this shape:

```json
[["VER", 92.608], ["LEC", 94.09], ["ALO", 94.199], ["PER", 94.364], ["NOR", 94.476]]
```

## 4. Run checks

```powershell
ruff check src tests
python -m pytest
python -m pytest -m integration
python -m pytest -m "integration or not integration"
docker compose config --quiet
git diff --check
```

The default pytest configuration excludes the PostgreSQL integration test;
run it separately with the local database available, or use the combined
marker expression above to run the complete suite in one command.

## 5. Optional exports and monitoring

The hosted exporter is allowlisted to core relational tables, omits raw
telemetry samples, and checks the local size against its 400 MB default cap.
Set `HOSTED_DATABASE_URL` only after selecting the destination database. Do
not run this command against a production or third-party database without
confirming that destination:

```powershell
python -m f1engine.export_hosted --max-mb 400
```

The current source estimate is 164,369 allowlisted rows and 35.41 MB.

Generate Valkey activity for BetterDB Monitor:

```powershell
python -m f1engine.bench_cache
python -m f1engine.leaderboard 2024 1
```

BetterDB's in-memory storage mode may not provide every key-analytics metric.
Add screenshots after a manual review of the local dashboard:

![BetterDB overview screenshot placeholder](./betterdb-overview.png)

![BetterDB slow-commands screenshot placeholder](./betterdb-slow-commands.png)
