# f1-telemetry-engine

A Python project for ingesting and analyzing Formula 1 telemetry.

## Overview

## Setup

1. Copy `.env.example` to `.env`. If `.env` already exists, add any missing settings without replacing existing credentials.
2. Update the local Postgres password and keep `.env` private; it is excluded from Git.
3. Start Docker Desktop, then start the services from the project root:

   ```powershell
   docker compose --env-file .env -f docker/compose.yaml up -d
   ```

4. Activate the Python environment and select the `f1-telemetry` Jupyter kernel:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

The Postgres and Valkey ports, database name, user, and connection URLs are configured in `.env`. The notebook loads `.env` and uses `FASTF1_CACHE_DIR` for its FastF1 cache. Valkey is available for future application use; it is not currently consumed by application code.

## Usage

Check service health and stop the containers with:

```powershell
docker compose --env-file .env -f docker/compose.yaml ps
docker compose --env-file .env -f docker/compose.yaml down
```

Open `notebooks/01_first_lap.ipynb` and run its cells with the `f1-telemetry` kernel.

## Architecture

## Roadmap
