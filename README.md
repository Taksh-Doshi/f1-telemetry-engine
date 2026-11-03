# f1-telemetry-engine

A Python project for ingesting and analyzing Formula 1 telemetry.

## Overview

This project collects Formula 1 session data and telemetry using FastF1.
It stores the data in Postgres so it can be queried and analyzed later.
The goal is to build a reliable, repeatable pipeline from race sessions
to useful lap and telemetry insights.

## Setup

1. Copy `.env.example` to `.env`. If `.env` already exists, add any missing settings without replacing existing credentials.
2. Update the local Postgres password and keep `.env` private; it is excluded from Git.
3. Start Docker Desktop, then start the services from the project root:

   ```powershell
   docker compose up -d
   ```

4. Activate the Python environment and select the `f1-telemetry` Jupyter kernel:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

5. From the project root, install the source-layout package in editable mode:

   ```powershell
   python -m pip install -e .
   ```

The Postgres and Valkey ports, database name, user, and connection URLs are configured in `.env`. The notebook loads `.env` and uses `FASTF1_CACHE_DIR` for its FastF1 cache. Valkey is available for future application use; it is not currently consumed by application code.

## Usage

Check service health and stop the containers with:

```powershell
docker compose ps
docker compose down
```

Open `notebooks/01_first_lap.ipynb` and run its cells with the `f1-telemetry` kernel.

Ingest one race session (the default session is `R` for Race). This also loads
car telemetry and stores one summary row per lap in
`lap_telemetry_summary`. FastF1 caches the downloaded session data, so reruns
can reuse the local cache:

```powershell
python -m f1engine.ingest 2024 1
```

Print row counts for the ingestion tables:

```powershell
python -m f1engine.counts
```

Raw telemetry samples are stored only when explicitly requested. Select drivers
by their FastF1 abbreviation (for example `VER,LEC`) or car number; omit
`--drivers` to store all drivers from that one session. This creates a
session-specific Postgres partition and is intentionally not part of season
ingestion because raw samples require much more storage than lap summaries:

```powershell
python -m f1engine.ingest 2024 1 --telemetry-samples --drivers VER,LEC
```

The race session and lap records must already be ingested. Re-running this
command is safe: samples are keyed by session, driver, and sample time, so
existing samples are skipped.

Ingest all race rounds in a season. Existing rounds are skipped only when both
their laps and telemetry summaries are already stored; otherwise, the command
fills in any missing data. Confirm the run before starting a full season:

```powershell
python -m f1engine.ingest --season 2024
```

Run one of the ten numbered SQL analysis queries and print its result:

```powershell
python -m f1engine.queries 1
```

The matching query files are in `sql/queries/`.

## Architecture

## Roadmap
