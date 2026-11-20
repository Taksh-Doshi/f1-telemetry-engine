"""Export and read telemetry_samples data as per-session Parquet files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from f1engine.db import get_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = PROJECT_ROOT / "data" / "parquet"
PARQUET_DIR = DEFAULT_PARQUET_DIR


def _require_pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export/read requires pyarrow; it is not installed in this environment"
        ) from exc
    return pa, pq


def session_filename(session_id: int) -> str:
    return f"telemetry_samples_session_{int(session_id)}.parquet"


def export_telemetry_samples(
    engine: Engine,
    output_dir: str | Path = DEFAULT_PARQUET_DIR,
    session_ids: Iterable[int] | None = None,
    batch_size: int = 50000,
) -> dict[int, Path]:
    """Export telemetry_samples to one Parquet file per session."""
    pa, pq = _require_pyarrow()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    if session_ids is None:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT DISTINCT session_id FROM telemetry_samples ORDER BY session_id")
            ).scalars().all()
        session_ids = [int(value) for value in rows]

    exported: dict[int, Path] = {}
    for session_id in session_ids:
        offset = 0
        frames = []
        while True:
            frame = pd.read_sql_query(
                text(
                    "SELECT * FROM telemetry_samples "
                    "WHERE session_id = :session_id "
                    "ORDER BY driver_id, time_seconds "
                    "LIMIT :limit OFFSET :offset"
                ),
                engine,
                params={"session_id": int(session_id), "limit": batch_size, "offset": offset},
            )
            if frame.empty:
                break
            frames.append(frame)
            if len(frame) < batch_size:
                break
            offset += len(frame)

        if not frames:
            continue
        dataframe = pd.concat(frames, ignore_index=True)
        path = destination / session_filename(int(session_id))
        try:
            pq.write_table(pa.Table.from_pandas(dataframe, preserve_index=False), path)
        except Exception as exc:
            raise RuntimeError(f"Failed to write Parquet file for session {session_id}") from exc
        exported[int(session_id)] = path
    return exported


def read_telemetry_samples(
    session_id: int | None = None,
    parquet_dir: str | Path = DEFAULT_PARQUET_DIR,
) -> pd.DataFrame:
    """Read one session or every per-session telemetry Parquet file."""
    _, pq = _require_pyarrow()
    directory = Path(parquet_dir)
    if not directory.exists():
        raise FileNotFoundError(f"Parquet directory does not exist: {directory}")

    if session_id is not None:
        paths = [directory / session_filename(int(session_id))]
        if not paths[0].exists():
            raise FileNotFoundError(
                f"No Parquet file found for telemetry session {int(session_id)}"
            )
    else:
        paths = sorted(directory.glob("telemetry_samples_session_*.parquet"))
        if not paths:
            raise FileNotFoundError(f"No telemetry Parquet files found in {directory}")

    frames = []
    for path in paths:
        try:
            frames.append(pq.read_table(path).to_pandas())
        except Exception as exc:
            raise RuntimeError(f"Failed to read Parquet file: {path.name}") from exc
    return pd.concat(frames, ignore_index=True)


def export_session_telemetry(
    engine: Engine, session_id: int, output_dir: str | Path = DEFAULT_PARQUET_DIR
) -> Path:
    return export_telemetry_samples(engine, output_dir, [session_id])[int(session_id)]


def read_session_telemetry(
    session_id: int, parquet_dir: str | Path = DEFAULT_PARQUET_DIR
) -> pd.DataFrame:
    return read_telemetry_samples(session_id, parquet_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export raw telemetry samples to local per-session Parquet files"
    )
    parser.add_argument("--session-id", type=int)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PARQUET_DIR)
    parser.add_argument("--batch-size", type=int, default=50000)
    args = parser.parse_args(argv)
    if args.session_id is not None and args.session_id <= 0:
        raise ValueError("--session-id must be positive")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    engine = get_engine()
    try:
        session_ids = None if args.session_id is None else [args.session_id]
        exported = export_telemetry_samples(
            engine,
            args.output_dir,
            session_ids=session_ids,
            batch_size=args.batch_size,
        )
    finally:
        engine.dispose()
    for session_id, path in exported.items():
        print(f"Session {session_id}: {path}")
    print(f"Exported {len(exported)} session file(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
