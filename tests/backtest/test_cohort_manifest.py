"""Tests for tools.backtest.cohort_manifest.

Covers Task 3.1 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``CohortManifest`` schema validation (cohort_id regex, as_of date type
  + future check, ticker uniqueness, market enum, benchmark enum,
  cost_cap_usd > 0).
- ``TickerEntry`` schema validation.
- ``load_cohort`` JSON loader (well-formed and malformed inputs).
- ``cohort_manifest_path`` resolves under repo root and validates the
  ``cohort_id`` first (so it is immune to path traversal).
- ``to_json`` round-trip with ``load_cohort``.
- Sample manifests (``smoke.json`` + ``2025Q1.json``) parse cleanly.

Run via: ``python -m pytest tests/backtest/test_cohort_manifest.py -v``
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

from tools.backtest.cohort_manifest import (  # noqa: E402
    CohortManifest,
    CohortManifestError,
    TickerEntry,
    cohort_manifest_path,
    load_cohort,
    to_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_BACKTEST_COHORTS = ROOT / "evals" / "backtest" / "cohorts"


def _valid_manifest_kwargs(**overrides):
    base = {
        "cohort_id": "test-cohort",
        "as_of": _dt.date(2025, 3, 31),
        "tickers": (TickerEntry(ticker="AAPL", market="US"),),
        "benchmark": "SPY",
        "mode": "C",
        "run_count": 1,
        "cost_cap_usd": 5.0,
        "notes": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Sample manifest happy paths
# ---------------------------------------------------------------------------


def test_load_smoke_cohort_manifest() -> None:
    path = REPO_BACKTEST_COHORTS / "smoke.json"
    manifest = load_cohort(path)
    assert manifest.cohort_id == "smoke"
    assert manifest.as_of == _dt.date(2025, 3, 31)
    assert len(manifest.tickers) == 1
    assert manifest.tickers[0].ticker == "AAPL"
    assert manifest.tickers[0].market == "US"
    assert manifest.benchmark == "SPY"
    assert manifest.mode == "C"
    assert manifest.run_count == 1
    assert manifest.cost_cap_usd == 5.0


def test_load_2025q1_cohort_manifest() -> None:
    path = REPO_BACKTEST_COHORTS / "2025Q1.json"
    manifest = load_cohort(path)
    assert manifest.cohort_id == "2025Q1"
    assert manifest.as_of == _dt.date(2025, 3, 31)
    assert len(manifest.tickers) == 30
    assert manifest.benchmark == "MIXED"
    assert manifest.mode == "C"
    assert manifest.cost_cap_usd == 50.0
    # All tickers are non-empty US market
    for entry in manifest.tickers:
        assert entry.ticker
        assert entry.market == "US"


# ---------------------------------------------------------------------------
# Validation: cohort_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        " ",
        "has spaces",
        "has/slash",
        "has\\backslash",
        "..",
        "../etc/passwd",
        "name!",
        "x" * 33,  # too long (max 32)
    ],
)
def test_invalid_cohort_id_rejected(bad_id: str) -> None:
    with pytest.raises(CohortManifestError, match="cohort_id"):
        CohortManifest(**_valid_manifest_kwargs(cohort_id=bad_id))


@pytest.mark.parametrize(
    "good_id",
    [
        "a",
        "2025Q1",
        "smoke",
        "test-cohort",
        "test_cohort",
        "Q1-2025",
        "x" * 32,
    ],
)
def test_valid_cohort_id_accepted(good_id: str) -> None:
    m = CohortManifest(**_valid_manifest_kwargs(cohort_id=good_id))
    assert m.cohort_id == good_id


# ---------------------------------------------------------------------------
# Validation: as_of
# ---------------------------------------------------------------------------


def test_future_as_of_rejected() -> None:
    future = _dt.date.today() + _dt.timedelta(days=1)
    with pytest.raises(CohortManifestError, match="as_of"):
        CohortManifest(**_valid_manifest_kwargs(as_of=future))


def test_today_as_of_accepted() -> None:
    today = _dt.date.today()
    m = CohortManifest(**_valid_manifest_kwargs(as_of=today))
    assert m.as_of == today


def test_datetime_as_of_rejected() -> None:
    bad = _dt.datetime(2025, 3, 31, 12, 0, 0, tzinfo=_dt.UTC)
    with pytest.raises(CohortManifestError, match="as_of"):
        CohortManifest(**_valid_manifest_kwargs(as_of=bad))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Validation: tickers
# ---------------------------------------------------------------------------


def test_empty_tickers_list_rejected() -> None:
    with pytest.raises(CohortManifestError, match="tickers"):
        CohortManifest(**_valid_manifest_kwargs(tickers=()))


def test_duplicate_tickers_rejected() -> None:
    tickers = (
        TickerEntry(ticker="AAPL", market="US"),
        TickerEntry(ticker="AAPL", market="US"),
    )
    with pytest.raises(CohortManifestError, match="duplicate"):
        CohortManifest(**_valid_manifest_kwargs(tickers=tickers))


def test_invalid_market_rejected() -> None:
    with pytest.raises(CohortManifestError, match="market"):
        TickerEntry(ticker="AAPL", market="JP")  # type: ignore[arg-type]


def test_empty_ticker_string_rejected() -> None:
    with pytest.raises(CohortManifestError, match="ticker"):
        TickerEntry(ticker="", market="US")


def test_tickers_must_be_tuple_or_list() -> None:
    # A list input should be coerced or accepted in load_cohort, but the
    # dataclass itself wants a tuple. A bare string would fail the
    # iteration / TickerEntry check.
    with pytest.raises(CohortManifestError):
        CohortManifest(**_valid_manifest_kwargs(tickers="AAPL"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Validation: benchmark, mode, cost_cap_usd, run_count
# ---------------------------------------------------------------------------


def test_unknown_benchmark_rejected() -> None:
    with pytest.raises(CohortManifestError, match="benchmark"):
        CohortManifest(**_valid_manifest_kwargs(benchmark="DAX"))  # type: ignore[arg-type]


def test_unknown_mode_rejected() -> None:
    with pytest.raises(CohortManifestError, match="mode"):
        CohortManifest(**_valid_manifest_kwargs(mode="A"))  # type: ignore[arg-type]


def test_negative_cost_cap_rejected() -> None:
    with pytest.raises(CohortManifestError, match="cost_cap_usd"):
        CohortManifest(**_valid_manifest_kwargs(cost_cap_usd=-1.0))


def test_zero_cost_cap_rejected() -> None:
    with pytest.raises(CohortManifestError, match="cost_cap_usd"):
        CohortManifest(**_valid_manifest_kwargs(cost_cap_usd=0.0))


def test_invalid_run_count_rejected() -> None:
    with pytest.raises(CohortManifestError, match="run_count"):
        CohortManifest(**_valid_manifest_kwargs(run_count=2))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_to_json_roundtrip(tmp_path: pathlib.Path) -> None:
    original = CohortManifest(
        **_valid_manifest_kwargs(
            cohort_id="round-trip",
            tickers=(
                TickerEntry(ticker="AAPL", market="US", notes="anchor"),
                TickerEntry(ticker="005930", market="KR"),
            ),
            benchmark="MIXED",
            cost_cap_usd=10.5,
            notes="round-trip test",
        )
    )

    json_text = to_json(original)
    assert json_text.endswith("\n")
    # Pretty-printed (multiple lines) and sorted keys
    assert json_text.count("\n") >= 5

    out_file = tmp_path / "round-trip.json"
    out_file.write_text(json_text, encoding="utf-8")

    reloaded = load_cohort(out_file)
    assert reloaded == original


def test_to_json_sorted_keys(tmp_path: pathlib.Path) -> None:
    m = CohortManifest(**_valid_manifest_kwargs())
    text = to_json(m)
    payload = json.loads(text)
    # Sorted keys at the top level
    assert list(payload.keys()) == sorted(payload.keys())


# ---------------------------------------------------------------------------
# load_cohort error paths
# ---------------------------------------------------------------------------


def test_load_malformed_json_raises(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{this is not json", encoding="utf-8")
    with pytest.raises(CohortManifestError, match="JSON"):
        load_cohort(bad)


def test_load_missing_required_field_raises(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "missing.json"
    bad.write_text(
        json.dumps({"as_of": "2025-03-31", "tickers": [{"ticker": "AAPL", "market": "US"}]}),
        encoding="utf-8",
    )
    with pytest.raises(CohortManifestError, match="cohort_id"):
        load_cohort(bad)


def test_load_nonexistent_file_raises(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(CohortManifestError):
        load_cohort(missing)


def test_load_invalid_as_of_string_raises(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad-date.json"
    bad.write_text(
        json.dumps(
            {
                "cohort_id": "x",
                "as_of": "not-a-date",
                "tickers": [{"ticker": "AAPL", "market": "US"}],
                "benchmark": "SPY",
                "mode": "C",
                "cost_cap_usd": 5.0,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CohortManifestError, match="as_of"):
        load_cohort(bad)


# ---------------------------------------------------------------------------
# cohort_manifest_path
# ---------------------------------------------------------------------------


def test_cohort_manifest_path_resolves() -> None:
    path = cohort_manifest_path("smoke")
    # under repo root
    assert ROOT in path.parents
    assert path.name == "smoke.json"
    assert path.parent.name == "cohorts"


@pytest.mark.parametrize(
    "bad_id",
    ["", "..", "../escape", "with/slash", "spaces here", "x" * 33],
)
def test_cohort_manifest_path_validates_id(bad_id: str) -> None:
    with pytest.raises(CohortManifestError, match="cohort_id"):
        cohort_manifest_path(bad_id)


# ---------------------------------------------------------------------------
# Frozen dataclass
# ---------------------------------------------------------------------------


def test_frozen_manifest() -> None:
    m = CohortManifest(**_valid_manifest_kwargs())
    with pytest.raises((FrozenInstanceError, AttributeError)):
        m.cohort_id = "new-id"  # type: ignore[misc]


def test_frozen_ticker_entry() -> None:
    entry = TickerEntry(ticker="AAPL", market="US")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        entry.ticker = "MSFT"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Regression tests for code-quality NIT fixes
# ---------------------------------------------------------------------------


def test_cost_cap_usd_rejects_bool() -> None:
    """bool is a subclass of int. cost_cap_usd=True would silently parse
    as a $1 budget — must be rejected."""
    kwargs = _valid_manifest_kwargs()
    kwargs["cost_cap_usd"] = True
    with pytest.raises(CohortManifestError, match="cost_cap_usd"):
        CohortManifest(**kwargs)


def test_cost_cap_usd_rejects_nan_and_inf() -> None:
    """NaN and Inf both pass `<= 0` checks because NaN comparisons return
    False and Inf is positive. Must be rejected to prevent the runner's
    budget guard from silently disabling."""
    import math

    kwargs = _valid_manifest_kwargs()
    kwargs["cost_cap_usd"] = math.nan
    with pytest.raises(CohortManifestError, match="finite"):
        CohortManifest(**kwargs)

    kwargs["cost_cap_usd"] = math.inf
    with pytest.raises(CohortManifestError, match="finite"):
        CohortManifest(**kwargs)


def test_run_count_rejects_bool() -> None:
    """True == 1 and True in {1, 3} is True — must reject bool explicitly
    so a typo'd run_count=true doesn't sneak through as 1."""
    kwargs = _valid_manifest_kwargs()
    kwargs["run_count"] = True
    with pytest.raises(CohortManifestError, match="run_count"):
        CohortManifest(**kwargs)


def test_manifest_notes_must_be_string() -> None:
    kwargs = _valid_manifest_kwargs()
    kwargs["notes"] = 42
    with pytest.raises(CohortManifestError, match="notes"):
        CohortManifest(**kwargs)


def test_ticker_entry_notes_must_be_string() -> None:
    with pytest.raises(CohortManifestError, match="notes"):
        TickerEntry(ticker="AAPL", market="US", notes=42)  # type: ignore[arg-type]


def test_load_cohort_rejects_unknown_top_level_keys(tmp_path: pathlib.Path) -> None:
    """A typo'd `benchamrk` would otherwise fall back silently to the
    default benchmark — strict reject prevents that whole bug class."""
    payload = {
        "cohort_id": "smoke",
        "as_of": "2025-03-31",
        "tickers": [{"ticker": "AAPL", "market": "US"}],
        "benchamrk": "QQQ",  # intentional typo
    }
    p = tmp_path / "typo.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CohortManifestError, match="unknown top-level"):
        load_cohort(p)


def test_load_cohort_rejects_unknown_ticker_keys(tmp_path: pathlib.Path) -> None:
    payload = {
        "cohort_id": "smoke",
        "as_of": "2025-03-31",
        "tickers": [{"ticker": "AAPL", "market": "US", "tikcer": "typo"}],
    }
    p = tmp_path / "typo.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CohortManifestError, match="unknown keys"):
        load_cohort(p)
