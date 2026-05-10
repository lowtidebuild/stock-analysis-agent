"""Tests for tools.backtest.pipeline_context.BacktestContext.

Covers Task 1.2 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``run_id`` formatting (timestamp + ticker + as-of date),
- ``artifact_root`` placement under ``backtest/cohorts/{cohort}/runs/{ticker}``
  and honoring ``$STOCK_ANALYSIS_DATA_DIR``,
- ``write_meta`` JSON contract (keys, freeze strategy, idempotence),
- frozen-dataclass invariants and timezone-aware default ``started_at``.

Run via: ``python -m pytest tests/backtest/test_pipeline_context.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reload_paths(monkeypatch: pytest.MonkeyPatch, data_dir: str | None) -> None:
    """Reset ``tools.paths`` so a new env var is picked up at import."""
    if data_dir is None:
        monkeypatch.delenv("STOCK_ANALYSIS_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", data_dir)
    sys.modules.pop("tools.backtest.pipeline_context", None)
    sys.modules.pop("tools.backtest", None)
    sys.modules.pop("tools.paths", None)


def _fixed_started_at() -> _dt.datetime:
    return _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)


def test_run_id_format(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
        started_at=_fixed_started_at(),
    )
    assert ctx.run_id() == "20260508T120000Z_AAPL_backtest_2025-03-31"


def test_artifact_root_under_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="MSFT",
        as_of=_dt.date(2025, 3, 31),
    )
    root = ctx.artifact_root()
    assert root.parts[-5:] == ("backtest", "cohorts", "2025Q1", "runs", "MSFT")
    # Spot-check the structural ancestry for readability.
    assert root.name == "MSFT"
    assert root.parent.name == "runs"
    assert root.parent.parent.name == "2025Q1"
    assert root.parent.parent.parent.name == "cohorts"
    assert root.parent.parent.parent.parent.name == "backtest"


def test_artifact_root_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    override = tmp_path / "agent-runtime"
    _reload_paths(monkeypatch, str(override))
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
    )
    expected = override / "backtest" / "cohorts" / "2025Q1" / "runs" / "AAPL"
    assert ctx.artifact_root() == expected


def test_write_meta_creates_dir_and_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    _reload_paths(monkeypatch, str(tmp_path))
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
        started_at=_fixed_started_at(),
    )
    ctx.write_meta()

    meta_file = ctx.meta_path()
    assert meta_file.exists()
    assert meta_file.parent == ctx.artifact_root()
    assert meta_file.name == "_backtest-meta.json"

    raw = meta_file.read_text(encoding="utf-8")
    assert raw.endswith("\n"), "meta JSON should end with a trailing newline"
    payload = json.loads(raw)

    expected_keys = {
        "as_of",
        "cohort_id",
        "freeze_strategy",
        "run_id",
        "started_at",
        "ticker",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["cohort_id"] == "2025Q1"
    assert payload["ticker"] == "AAPL"
    assert payload["as_of"] == "2025-03-31"
    assert payload["freeze_strategy"] == "hybrid"
    assert payload["run_id"] == "20260508T120000Z_AAPL_backtest_2025-03-31"

    # started_at is a parseable ISO-8601 string
    assert isinstance(payload["started_at"], str)
    parsed = _dt.datetime.fromisoformat(payload["started_at"])
    assert parsed.tzinfo is not None


def test_write_meta_overwrites_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    _reload_paths(monkeypatch, str(tmp_path))
    from tools.backtest.pipeline_context import BacktestContext

    first = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
        started_at=_dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC),
    )
    first.write_meta()

    second = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
        started_at=_dt.datetime(2026, 5, 8, 13, 30, 0, tzinfo=_dt.UTC),
    )
    second.write_meta()  # must not raise

    payload = json.loads(second.meta_path().read_text(encoding="utf-8"))
    assert payload["run_id"] == second.run_id()
    assert payload["started_at"] == second.started_at.isoformat()


def test_default_freeze_strategy_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
    )
    assert ctx.freeze_strategy == "hybrid"


def test_default_started_at_is_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
    )
    assert ctx.started_at.tzinfo is not None
    assert ctx.started_at.utcoffset() == _dt.timedelta(0)


def test_frozen_dataclass(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    ctx = BacktestContext(
        cohort_id="2025Q1",
        ticker="AAPL",
        as_of=_dt.date(2025, 3, 31),
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        ctx.ticker = "MSFT"  # type: ignore[misc]


def test_naive_started_at_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    naive = _dt.datetime(2026, 5, 8, 12, 0, 0)
    assert naive.tzinfo is None
    with pytest.raises(ValueError, match="timezone-aware"):
        BacktestContext(
            cohort_id="2025Q1",
            ticker="AAPL",
            as_of=_dt.date(2025, 3, 31),
            started_at=naive,
        )


def test_datetime_passed_as_as_of_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_paths(monkeypatch, None)
    from tools.backtest.pipeline_context import BacktestContext

    with pytest.raises(TypeError, match="datetime.date"):
        BacktestContext(
            cohort_id="2025Q1",
            ticker="AAPL",
            as_of=_dt.datetime(2025, 3, 31, 14, 30, tzinfo=_dt.UTC),  # type: ignore[arg-type]
        )
