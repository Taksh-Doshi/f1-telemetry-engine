from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

from f1engine import export_hosted, export_parquet


def test_hosted_allowlist_and_fk_order():
    assert export_hosted.TABLES == (
        "events",
        "sessions",
        "drivers",
        "laps",
        "stints",
        "weather",
        "lap_telemetry_summary",
    )


def test_hosted_refuses_oversized_export(monkeypatch, capsys):
    source = Mock()
    target = Mock()
    create_target = Mock(return_value=target)
    monkeypatch.setattr(export_hosted, "load_local_env", lambda: None)
    monkeypatch.setattr(export_hosted.os, "environ", {"HOSTED_DATABASE_URL": "postgresql://example"})
    monkeypatch.setattr(export_hosted, "get_engine", lambda: source)
    monkeypatch.setattr(export_hosted, "create_engine", create_target)
    monkeypatch.setattr(export_hosted, "run_schema", lambda engine: None)
    monkeypatch.setattr(
        export_hosted,
        "estimate_table_stats",
        lambda engine: {
            "events": {"rows": 2, "size_bytes": 401 * 1024 * 1024},
        },
    )

    with pytest.raises(RuntimeError, match="Refusing export"):
        export_hosted.main(["--target-url-env", "HOSTED_DATABASE_URL", "--max-mb", "400"])

    source.dispose.assert_called_once()
    create_target.assert_not_called()
    target.dispose.assert_not_called()
    assert "HOSTED_DATABASE_URL" not in capsys.readouterr().out


def test_fetch_table_rows_never_allows_unlisted_table():
    with pytest.raises(ValueError, match="non-allowlisted"):
        list(export_hosted.fetch_table_rows(Mock(), "telemetry_samples"))


def test_copy_table_uses_batches(monkeypatch):
    source = Mock()
    target = MagicMock()
    target.begin.return_value.__enter__.return_value = Mock()
    table = Mock()
    table.c.keys.return_value = ["event_id", "event_name"]
    monkeypatch.setattr(export_hosted, "Table", lambda *a, **k: table)
    dialect_insert = Mock()
    statement = Mock()
    dialect_insert.return_value.values.return_value.on_conflict_do_nothing.return_value = statement
    monkeypatch.setattr(export_hosted, "insert", dialect_insert)

    batches = [
        [{"event_id": 1, "event_name": "Race"}],
        [{"event_id": 2, "event_name": "Sprint"}],
    ]
    monkeypatch.setattr(export_hosted, "fetch_table_rows", lambda *a, **k: iter(batches))

    count = export_hosted.copy_table(source, target, "events", batch_size=1)

    assert count == 2
    target.begin.assert_called_once()


def test_parquet_missing_dependency_is_clear(monkeypatch, tmp_path):
    monkeypatch.setattr(
        export_parquet,
        "_require_pyarrow",
        lambda: (_ for _ in ()).throw(
            RuntimeError("Parquet export/read requires pyarrow; it is not installed")
        ),
    )
    with pytest.raises(RuntimeError, match="pyarrow"):
        export_parquet.export_telemetry_samples(Mock(), tmp_path)
