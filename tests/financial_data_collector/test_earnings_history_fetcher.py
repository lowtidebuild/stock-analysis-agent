"""Tests for the Phase F.2 earnings-history-fetcher.

The earnings-history-fetcher script is invoked by the orchestrator inside
Mode E (Preview + Review) to populate beat/miss history and 1-day stock
reaction metrics for the last N quarters.

Contract for the script:

* Programmatic surface (these tests):
  - ``fetch_earnings_history(ticker, yf_module=None, timeout=30, quarters=8)``
    returns one dict with the schema described below.
  - ``fetch_earnings_history_many(tickers, output_dir, yf_module=None,
    timeout=30, quarters=8)`` writes one JSON per ticker into ``output_dir``;
    returns a list of result dicts. One bad ticker does not abort siblings.

* Per-ticker JSON shape::

      {
        "ticker": "GOOGL",
        "collection_timestamp": "2026-05-07T12:00:00Z",
        "quarters": [
          {
            "quarter": "Q1 2026",
            "report_date": "2026-04-29",
            "actual_eps": 5.11,
            "consensus_eps": 2.63,
            "surprise_pct": 94.3,
            "beat": true,
            "stock_reaction_1d_pct": 6.5
          },
          ...
        ],
        "summary": {
          "quarters_count": 8,
          "hit_rate": 0.875,
          "avg_surprise_pct": 12.4,
          "avg_reaction_1d_pct": 3.2
        },
        "_sanitization": {...}
      }

* Sanitization block always present (CLAUDE.md §12 trust boundary).
* Per-ticker errors NEVER raise (one bad ticker does not abort siblings).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EARNINGS_HISTORY_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "financial-data-collector"
    / "scripts"
    / "earnings-history-fetcher.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "earnings_history_fetcher", EARNINGS_HISTORY_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(
            f"failed to load earnings-history-fetcher.py from {EARNINGS_HISTORY_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# yfinance test doubles
# ---------------------------------------------------------------------------


class _FakeIndex:
    """Iterable that mimics a pandas DatetimeIndex (for earnings_history)."""

    def __init__(self, dates):
        self._dates = list(dates)

    def __iter__(self):
        return iter(self._dates)

    def __len__(self):
        return len(self._dates)


class _FakeEarningsHistoryDF:
    """Mimics yfinance ``earnings_history`` DataFrame.

    The real object exposes columns ``epsActual``, ``epsEstimate``,
    ``epsDifference``, and ``surprisePercent``. The fetcher only needs the
    actual + estimate (it computes surprise itself for consistency) and the
    report date (the index).
    """

    def __init__(self, rows):
        # rows: list of dicts, each having keys
        # report_date (date), epsActual, epsEstimate, epsDifference, surprisePercent
        self._rows = list(rows)
        self.empty = len(rows) == 0
        self.index = _FakeIndex([r["report_date"] for r in rows])

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)

    # The fetcher iterates rows by index; expose iterrows() for parity with
    # pandas DataFrame.
    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield row["report_date"], row


class _FakeHistoryRow:
    """Single row of the price-history DataFrame (date → close)."""

    def __init__(self, close):
        self.close = close


class _FakePriceHistoryDF:
    """Mimics yfinance ``Ticker.history()`` price DataFrame.

    Provides ``.loc[date_str, "Close"]`` / ``.iloc`` access patterns the
    fetcher uses to compute 1-day stock reactions.
    """

    def __init__(self, closes_by_date):
        # closes_by_date: dict[date, float]
        self._closes = dict(closes_by_date)
        # sorted ascending
        self._sorted_dates = sorted(self._closes.keys())
        self.empty = len(self._closes) == 0

    @property
    def index(self):
        return _FakeIndex(self._sorted_dates)

    def get_close_on(self, d):
        return self._closes.get(d)

    def get_close_on_or_before(self, d):
        for sd in reversed(self._sorted_dates):
            if sd <= d:
                return self._closes[sd]
        return None

    def get_close_on_or_after(self, d):
        for sd in self._sorted_dates:
            if sd >= d:
                return self._closes[sd]
        return None


class _FakeHistoryTicker:
    """Mimics ``yfinance.Ticker(t)`` for earnings-history calls."""

    def __init__(
        self,
        earnings_history=None,
        price_history=None,
        earnings_history_raises=None,
        history_raises=None,
    ):
        self._earnings_history = earnings_history
        self._price_history = price_history
        self._earnings_history_raises = earnings_history_raises
        self._history_raises = history_raises

    @property
    def earnings_history(self):
        if self._earnings_history_raises is not None:
            raise self._earnings_history_raises
        return self._earnings_history

    def history(self, start=None, end=None, **_):
        if self._history_raises is not None:
            raise self._history_raises
        return self._price_history


class _FakeYFinance:
    """Mimics the top-level ``yfinance`` module."""

    def __init__(self, table):
        self._table = table
        self.calls: list[str] = []

    def Ticker(self, symbol: str):  # noqa: N802
        self.calls.append(symbol)
        spec = self._table.get(symbol)
        if isinstance(spec, BaseException):
            raise spec
        if spec is None:
            return _FakeHistoryTicker(
                earnings_history=_FakeEarningsHistoryDF([]),
                price_history=_FakePriceHistoryDF({}),
            )
        return spec


# ---------------------------------------------------------------------------
# Helpers: build canonical 8-quarter history
# ---------------------------------------------------------------------------


def _row(report_date, actual, estimate):
    diff = actual - estimate
    surprise_pct = (diff / abs(estimate) * 100) if estimate else 0.0
    return {
        "report_date": report_date,
        "epsActual": actual,
        "epsEstimate": estimate,
        "epsDifference": diff,
        "surprisePercent": surprise_pct,
    }


def _build_8q_history(
    base: date | None = None,
):
    """Generate 8 quarters back from the most recent (Q1 2026 → Q2 2024)."""
    base = base or date(2026, 4, 29)
    rows = []
    for i in range(8):
        report_date = base - timedelta(days=90 * i)
        # Alternating beat/miss: even i → beat, odd i → tiny miss
        if i % 2 == 0:
            actual = 5.11 - i * 0.10
            estimate = actual - 0.50
        else:
            actual = 4.20 - i * 0.05
            estimate = actual + 0.05  # miss
        rows.append(_row(report_date, actual, estimate))
    # The fetcher should not assume input order; we feed newest-first to mimic
    # yfinance default.
    return rows


def _build_price_history_for(rows, gap_pct=0.05):
    """Build a synthetic price-history that yields a known 1-day reaction."""
    closes = {}
    for i, row in enumerate(rows):
        d = row["report_date"]
        prev_close = 100.0 + i  # arbitrary distinct anchor per quarter
        next_close = prev_close * (1 + gap_pct)  # always +5%
        closes[d] = prev_close
        closes[d + timedelta(days=1)] = next_close
    return closes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class EarningsHistoryFetcherTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="earnings_history_test_"))
        self.output_dir = self.tmp / "run" / "history"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.module = _load_module()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class EarningsHistorySchemaTests(EarningsHistoryFetcherTestBase):
    """Test 1: 8-quarter history → full schema with summary."""

    def test_fetch_earnings_history_returns_full_schema(self) -> None:
        rows = _build_8q_history()
        prices = _build_price_history_for(rows, gap_pct=0.05)
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="GOOGL",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        for key in (
            "ticker",
            "collection_timestamp",
            "quarters",
            "summary",
            "_sanitization",
        ):
            self.assertIn(key, record, f"missing top-level key: {key}")

        self.assertEqual(record["ticker"], "GOOGL")
        self.assertEqual(len(record["quarters"]), 8)

        for q in record["quarters"]:
            for key in (
                "quarter",
                "report_date",
                "actual_eps",
                "consensus_eps",
                "surprise_pct",
                "beat",
                "stock_reaction_1d_pct",
            ):
                self.assertIn(key, q, f"missing quarter key: {key}")

        # Sanitization
        san = record["_sanitization"]
        self.assertEqual(san["tool"], "tools/prompt_injection_filter.py")


class EarningsHistoryHitRateTests(EarningsHistoryFetcherTestBase):
    """Test 2: hit_rate matches the alternating-beat fixture (4/8 beats)."""

    def test_hit_rate_calculation(self) -> None:
        rows = _build_8q_history()  # 4 beats (i=0,2,4,6), 4 misses (i=1,3,5,7)
        prices = _build_price_history_for(rows)
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="GOOGL",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        summary = record["summary"]
        self.assertEqual(summary["quarters_count"], 8)
        self.assertAlmostEqual(summary["hit_rate"], 0.5, places=3)


class EarningsHistoryAvgSurpriseTests(EarningsHistoryFetcherTestBase):
    """Test 3: avg_surprise_pct equals mean of per-quarter surprise %."""

    def test_avg_surprise_calculation(self) -> None:
        # All-beat fixture: actual=11, estimate=10 → +10% each
        base = date(2026, 4, 29)
        rows = []
        for i in range(4):
            d = base - timedelta(days=90 * i)
            rows.append(_row(d, actual=11.0, estimate=10.0))
        prices = _build_price_history_for(rows, gap_pct=0.03)  # +3% each

        yf = _FakeYFinance(
            {
                "ALLBEAT": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="ALLBEAT",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        summary = record["summary"]
        self.assertEqual(summary["quarters_count"], 4)
        self.assertAlmostEqual(summary["hit_rate"], 1.0, places=3)
        self.assertAlmostEqual(summary["avg_surprise_pct"], 10.0, places=2)
        self.assertAlmostEqual(summary["avg_reaction_1d_pct"], 3.0, places=2)


class EarningsHistoryMissingConsensusTests(EarningsHistoryFetcherTestBase):
    """Test 4: rows with missing consensus → excluded from summary, kept in
    quarters list with surprise_pct=None."""

    def test_missing_consensus_skipped_from_summary(self) -> None:
        base = date(2026, 4, 29)
        # 4 rows: 2 normal beats (+10%), 2 with None estimate (skip from summary)
        rows = [
            _row(base - timedelta(days=0), actual=11.0, estimate=10.0),  # +10%
            {
                "report_date": base - timedelta(days=90),
                "epsActual": 5.0,
                "epsEstimate": None,
                "epsDifference": None,
                "surprisePercent": None,
            },
            _row(base - timedelta(days=180), actual=11.0, estimate=10.0),  # +10%
            {
                "report_date": base - timedelta(days=270),
                "epsActual": None,
                "epsEstimate": 4.0,
                "epsDifference": None,
                "surprisePercent": None,
            },
        ]
        prices = _build_price_history_for(rows, gap_pct=0.04)

        yf = _FakeYFinance(
            {
                "MIXED": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="MIXED",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        # All 4 quarters retained, but summary computed only on the 2 with
        # full data.
        self.assertEqual(len(record["quarters"]), 4)

        # The two rows with None consensus/actual must have surprise_pct=None.
        none_quarters = [
            q for q in record["quarters"] if q.get("surprise_pct") is None
        ]
        self.assertEqual(len(none_quarters), 2)

        summary = record["summary"]
        # quarters_count = total quarters returned (4), but summary aggregates
        # only the rows with full data: hit_rate over 2 → 1.0, avg_surprise=10.
        self.assertEqual(summary["quarters_count"], 4)
        self.assertAlmostEqual(summary["hit_rate"], 1.0, places=3)
        self.assertAlmostEqual(summary["avg_surprise_pct"], 10.0, places=2)


class EarningsHistoryEmptyTests(EarningsHistoryFetcherTestBase):
    """Test 5: empty earnings_history → quarters=[], summary zeroes."""

    def test_empty_history_returns_empty_quarters_and_zero_summary(self) -> None:
        yf = _FakeYFinance(
            {
                "EMPTY": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF([]),
                    price_history=_FakePriceHistoryDF({}),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="EMPTY",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        self.assertEqual(record["quarters"], [])
        summary = record["summary"]
        self.assertEqual(summary["quarters_count"], 0)
        # The contract: no data → null (not zero) for averages.
        self.assertIsNone(summary.get("hit_rate"))
        self.assertIsNone(summary.get("avg_surprise_pct"))
        self.assertIsNone(summary.get("avg_reaction_1d_pct"))
        self.assertIn("_sanitization", record)


class EarningsHistorySanitizationTests(EarningsHistoryFetcherTestBase):
    """Test 6: sanitization block always present, even on graceful failure."""

    def test_sanitization_present_on_success(self) -> None:
        rows = _build_8q_history()
        prices = _build_price_history_for(rows)
        yf = _FakeYFinance(
            {
                "OK": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="OK",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        self.assertIn("_sanitization", record)
        san = record["_sanitization"]
        self.assertEqual(san["tool"], "tools/prompt_injection_filter.py")
        self.assertIn("version", san)
        self.assertIn("redactions", san)
        self.assertIn("findings", san)

    def test_sanitization_present_on_exception(self) -> None:
        yf = _FakeYFinance(
            {
                "BAD": _FakeHistoryTicker(
                    earnings_history_raises=RuntimeError("boom"),
                )
            }
        )

        # MUST NOT raise.
        record = self.module.fetch_earnings_history(
            ticker="BAD",
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        self.assertEqual(record["ticker"], "BAD")
        self.assertEqual(record["quarters"], [])
        self.assertIn("_sanitization", record)
        # Surface the error so caller can flag.
        self.assertIn("error", record)


class EarningsHistoryMultiTickerTests(EarningsHistoryFetcherTestBase):
    """Test 7: fetch_earnings_history_many writes one file per ticker; one bad
    ticker does not abort siblings."""

    def test_multi_ticker_writes_one_file_per_ticker(self) -> None:
        rows = _build_8q_history()
        prices = _build_price_history_for(rows)
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                ),
                "EMPTY": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF([]),
                    price_history=_FakePriceHistoryDF({}),
                ),
                "BOOM": RuntimeError("ticker constructor failed"),
            }
        )

        results = self.module.fetch_earnings_history_many(
            tickers=["GOOGL", "EMPTY", "BOOM"],
            output_dir=self.output_dir,
            yf_module=yf,
            timeout=5,
            quarters=8,
        )

        self.assertEqual(len(results), 3)
        by_ticker = {r["ticker"]: r for r in results}

        self.assertEqual(len(by_ticker["GOOGL"]["quarters"]), 8)
        self.assertEqual(by_ticker["EMPTY"]["quarters"], [])
        self.assertIn("error", by_ticker["BOOM"])

        for tkr in ("GOOGL", "EMPTY", "BOOM"):
            out = self.output_dir / f"{tkr}.json"
            self.assertTrue(out.exists(), f"{tkr}.json missing in output_dir")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["ticker"], tkr)
            self.assertIn("_sanitization", payload)


class EarningsHistoryQuartersLimitTests(EarningsHistoryFetcherTestBase):
    """Test 8: more than N quarters available → only the N most recent
    returned."""

    def test_quarters_argument_limits_returned_history(self) -> None:
        # 12 rows of history but only 4 should be returned.
        base = date(2026, 4, 29)
        rows = []
        for i in range(12):
            d = base - timedelta(days=90 * i)
            rows.append(_row(d, actual=11.0, estimate=10.0))
        prices = _build_price_history_for(rows, gap_pct=0.02)
        yf = _FakeYFinance(
            {
                "BIG": _FakeHistoryTicker(
                    earnings_history=_FakeEarningsHistoryDF(rows),
                    price_history=_FakePriceHistoryDF(prices),
                )
            }
        )

        record = self.module.fetch_earnings_history(
            ticker="BIG",
            yf_module=yf,
            timeout=5,
            quarters=4,
        )

        self.assertEqual(len(record["quarters"]), 4)
        # Most-recent first: report_date ordering should be reverse-chronological.
        report_dates = [q["report_date"] for q in record["quarters"]]
        sorted_desc = sorted(report_dates, reverse=True)
        self.assertEqual(report_dates, sorted_desc)


class EarningsHistoryModuleSurfaceTests(unittest.TestCase):
    """Sanity: the module exposes the expected surface."""

    def test_module_exposes_public_api(self) -> None:
        module = _load_module()
        self.assertTrue(hasattr(module, "fetch_earnings_history"))
        self.assertTrue(callable(module.fetch_earnings_history))
        self.assertTrue(hasattr(module, "fetch_earnings_history_many"))
        self.assertTrue(callable(module.fetch_earnings_history_many))
        # CLAUDE.md §12: collector must wire prompt-injection sanitizer.
        self.assertTrue(hasattr(module, "sanitize_record"))
        self.assertTrue(callable(module.sanitize_record))


if __name__ == "__main__":
    unittest.main()
