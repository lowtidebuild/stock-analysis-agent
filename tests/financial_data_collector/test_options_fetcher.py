"""Tests for the Phase F.2 options-fetcher (options-fetcher.py).

The options-fetcher script is invoked by the orchestrator inside Mode E
(Preview only) to populate ATM straddle / implied move data for the
earnings preview header.

Contract for the script:

* Programmatic surface (these tests):
  - ``fetch_options(ticker, yf_module=None, timeout=30)`` returns one dict
    with the schema described below.
  - ``fetch_options_many(tickers, output_dir, yf_module=None, timeout=30)``
    writes one JSON per ticker into ``output_dir``; returns a list of
    result dicts. One bad ticker does not abort the others.

* Per-ticker JSON contains the keys::

      ticker, as_of, spot_price, nearest_expiry, atm_strike,
      atm_call_price, atm_put_price, atm_straddle_price,
      implied_move_pct, iv_percentile, expiry_offset_days,
      _sanitization

* Graceful failure (per OD-F2): yfinance options-chain failures NEVER
  raise. Numeric fields become null and the record carries
  ``status="unavailable"`` plus an ``error`` message.

* Sanitization block always present (CLAUDE.md §12 trust boundary).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
OPTIONS_FETCHER_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "financial-data-collector"
    / "scripts"
    / "options-fetcher.py"
)


def _load_options_fetcher():
    spec = importlib.util.spec_from_file_location(
        "options_fetcher", OPTIONS_FETCHER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(
            f"failed to load options-fetcher.py from {OPTIONS_FETCHER_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# yfinance test doubles
# ---------------------------------------------------------------------------


class _FakeChain:
    """Mimics yfinance ``option_chain(expiry)`` return value (calls, puts)."""

    def __init__(self, calls, puts):
        self.calls = calls
        self.puts = puts


class _FakeOptionsTicker:
    """Mimics ``yfinance.Ticker(t)`` for options-related calls."""

    def __init__(
        self,
        options=None,
        chain_by_expiry=None,
        spot_price=None,
        info=None,
        options_raises=None,
        chain_raises=None,
    ):
        self._options = options or []
        self._chain_by_expiry = chain_by_expiry or {}
        self._spot_price = spot_price
        self._info = info or {}
        self._options_raises = options_raises
        self._chain_raises = chain_raises
        self.option_chain_calls: list[str] = []

    @property
    def options(self):
        if self._options_raises is not None:
            raise self._options_raises
        return self._options

    def option_chain(self, expiry: str):
        self.option_chain_calls.append(expiry)
        if self._chain_raises is not None:
            raise self._chain_raises
        chain = self._chain_by_expiry.get(expiry)
        if chain is None:
            return _FakeChain(calls=[], puts=[])
        return chain

    @property
    def fast_info(self):
        if self._spot_price is None:
            return {}
        return {"last_price": self._spot_price}

    @property
    def info(self):
        return self._info


class _FakeYFinance:
    """Mimics the top-level ``yfinance`` module."""

    def __init__(self, table):
        self._table = table
        self.calls: list[str] = []

    def Ticker(self, symbol: str):  # noqa: N802 (yfinance API)
        self.calls.append(symbol)
        spec = self._table.get(symbol)
        if isinstance(spec, BaseException):
            raise spec
        if spec is None:
            return _FakeOptionsTicker(options=[])
        return spec


# ---------------------------------------------------------------------------
# Helpers: build calls/puts rows
# ---------------------------------------------------------------------------


def _row(strike, last_price, bid=None, ask=None):
    """A single options row (dict-like). The fetcher must accept dicts."""
    return {
        "strike": strike,
        "lastPrice": last_price,
        "bid": bid if bid is not None else last_price - 0.05,
        "ask": ask if ask is not None else last_price + 0.05,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class OptionsFetcherTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="options_fetcher_test_"))
        self.output_dir = self.tmp / "run" / "options"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.module = _load_options_fetcher()
        self.today_iso = "2026-05-07"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class OptionsFetcherSchemaTests(OptionsFetcherTestBase):
    """Test 1: well-formed option_chain → full schema with computed values."""

    def test_fetch_options_returns_full_schema(self) -> None:
        expiry = "2026-05-09"
        spot = 388.43
        calls = [
            _row(380, 9.30),
            _row(385, 6.10),
            _row(388, 4.20),  # ATM (closest to spot)
            _row(390, 3.10),
            _row(395, 1.40),
        ]
        puts = [
            _row(380, 0.80),
            _row(385, 1.90),
            _row(388, 4.05),  # ATM
            _row(390, 5.30),
            _row(395, 8.20),
        ]
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeOptionsTicker(
                    options=[expiry, "2026-05-16", "2026-06-20"],
                    chain_by_expiry={expiry: _FakeChain(calls=calls, puts=puts)},
                    spot_price=spot,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="GOOGL",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        for key in (
            "ticker",
            "as_of",
            "spot_price",
            "nearest_expiry",
            "atm_strike",
            "atm_call_price",
            "atm_put_price",
            "atm_straddle_price",
            "implied_move_pct",
            "iv_percentile",
            "expiry_offset_days",
            "_sanitization",
        ):
            self.assertIn(key, record, f"missing top-level key: {key}")

        self.assertEqual(record["ticker"], "GOOGL")
        self.assertEqual(record["nearest_expiry"], expiry)
        self.assertEqual(record["atm_strike"], 388)
        self.assertAlmostEqual(record["atm_call_price"], 4.20, places=2)
        self.assertAlmostEqual(record["atm_put_price"], 4.05, places=2)
        self.assertAlmostEqual(record["atm_straddle_price"], 8.25, places=2)
        # implied_move = 8.25 / 388.43 * 100 ≈ 2.124%
        self.assertAlmostEqual(record["implied_move_pct"], 2.12, places=2)
        # iv_percentile not yet computed (left null in MVP)
        self.assertIsNone(record["iv_percentile"])
        # 2026-05-09 - 2026-05-07 = 2 days
        self.assertEqual(record["expiry_offset_days"], 2)
        # No status field on success.
        self.assertNotEqual(record.get("status"), "unavailable")


class OptionsFetcherATMStrikePickingTests(OptionsFetcherTestBase):
    """Test 2: ATM strike is the strike closest to spot, even when not exact."""

    def test_atm_strike_picks_closest_to_spot(self) -> None:
        expiry = "2026-05-09"
        spot = 392.10
        # spot=392.10; strikes 385/390/395 → 390 is closest (|390-392.10|=2.10)
        calls = [
            _row(385, 8.50),
            _row(390, 5.10),  # ATM
            _row(395, 2.40),
        ]
        puts = [
            _row(385, 1.10),
            _row(390, 3.00),  # ATM
            _row(395, 6.30),
        ]
        yf = _FakeYFinance(
            {
                "AAPL": _FakeOptionsTicker(
                    options=[expiry],
                    chain_by_expiry={expiry: _FakeChain(calls=calls, puts=puts)},
                    spot_price=spot,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="AAPL",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(record["atm_strike"], 390)
        self.assertAlmostEqual(record["atm_call_price"], 5.10, places=2)
        self.assertAlmostEqual(record["atm_put_price"], 3.00, places=2)
        self.assertAlmostEqual(record["atm_straddle_price"], 8.10, places=2)


class OptionsFetcherEmptyOptionsTests(OptionsFetcherTestBase):
    """Test 3: Ticker.options returns empty list → graceful unavailable record."""

    def test_empty_options_list_returns_unavailable_status(self) -> None:
        yf = _FakeYFinance(
            {
                "EMPTY": _FakeOptionsTicker(
                    options=[],  # no option expiries at all
                    spot_price=100.0,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="EMPTY",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(record["ticker"], "EMPTY")
        self.assertEqual(record.get("status"), "unavailable")
        self.assertIsNone(record["nearest_expiry"])
        self.assertIsNone(record["atm_strike"])
        self.assertIsNone(record["atm_call_price"])
        self.assertIsNone(record["atm_put_price"])
        self.assertIsNone(record["atm_straddle_price"])
        self.assertIsNone(record["implied_move_pct"])
        self.assertIn("error", record)
        self.assertIn("_sanitization", record)


class OptionsFetcherEmptyChainTests(OptionsFetcherTestBase):
    """Test 4: option_chain returns empty calls/puts → graceful unavailable."""

    def test_empty_chain_returns_unavailable_status(self) -> None:
        expiry = "2026-05-09"
        yf = _FakeYFinance(
            {
                "EMPTYCHAIN": _FakeOptionsTicker(
                    options=[expiry],
                    chain_by_expiry={expiry: _FakeChain(calls=[], puts=[])},
                    spot_price=200.0,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="EMPTYCHAIN",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(record.get("status"), "unavailable")
        self.assertIsNone(record["atm_call_price"])
        self.assertIsNone(record["atm_put_price"])
        self.assertIsNone(record["implied_move_pct"])
        self.assertIn("_sanitization", record)


class OptionsFetcherChainExceptionTests(OptionsFetcherTestBase):
    """Test 5: option_chain raises → graceful unavailable per OD-F2 (no raise)."""

    def test_chain_exception_returns_unavailable_status(self) -> None:
        yf = _FakeYFinance(
            {
                "BOOM": _FakeOptionsTicker(
                    options=["2026-05-09"],
                    chain_raises=RuntimeError("yfinance options chain exploded"),
                    spot_price=100.0,
                )
            }
        )

        # MUST NOT raise
        record = self.module.fetch_options(
            ticker="BOOM",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(record.get("status"), "unavailable")
        self.assertIn("error", record)
        self.assertIsNone(record["implied_move_pct"])
        self.assertIn("_sanitization", record)


class OptionsFetcherSpotFromInfoFallbackTests(OptionsFetcherTestBase):
    """Test 6: fast_info empty → fall back to info["regularMarketPrice"]."""

    def test_spot_falls_back_to_info_when_fast_info_missing(self) -> None:
        expiry = "2026-05-09"
        calls = [_row(100, 2.10)]
        puts = [_row(100, 1.90)]
        yf = _FakeYFinance(
            {
                "INFOSP": _FakeOptionsTicker(
                    options=[expiry],
                    chain_by_expiry={expiry: _FakeChain(calls=calls, puts=puts)},
                    spot_price=None,  # fast_info empty
                    info={"regularMarketPrice": 100.5},
                )
            }
        )

        record = self.module.fetch_options(
            ticker="INFOSP",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertAlmostEqual(record["spot_price"], 100.5, places=2)
        self.assertEqual(record["atm_strike"], 100)


class OptionsFetcherSanitizationTests(OptionsFetcherTestBase):
    """Test 7: sanitization block always present, even on graceful failure."""

    def test_sanitization_present_on_success(self) -> None:
        expiry = "2026-05-09"
        calls = [_row(100, 2.0)]
        puts = [_row(100, 2.0)]
        yf = _FakeYFinance(
            {
                "GOOD": _FakeOptionsTicker(
                    options=[expiry],
                    chain_by_expiry={expiry: _FakeChain(calls=calls, puts=puts)},
                    spot_price=100.0,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="GOOD",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertIn("_sanitization", record)
        san = record["_sanitization"]
        self.assertEqual(san["tool"], "tools/prompt_injection_filter.py")
        self.assertIn("version", san)
        self.assertIn("redactions", san)
        self.assertIn("findings", san)

    def test_sanitization_present_on_unavailable(self) -> None:
        yf = _FakeYFinance(
            {
                "BAD": _FakeOptionsTicker(
                    options_raises=RuntimeError("boom"),
                )
            }
        )
        record = self.module.fetch_options(
            ticker="BAD",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )
        self.assertEqual(record.get("status"), "unavailable")
        self.assertIn("_sanitization", record)


class OptionsFetcherMultiTickerTests(OptionsFetcherTestBase):
    """Test 8: fetch_options_many writes one file per ticker; one bad ticker
    does not abort the run."""

    def test_fetch_options_many_writes_one_file_per_ticker(self) -> None:
        expiry = "2026-05-09"
        calls = [_row(100, 2.0)]
        puts = [_row(100, 2.0)]
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeOptionsTicker(
                    options=[expiry],
                    chain_by_expiry={expiry: _FakeChain(calls=calls, puts=puts)},
                    spot_price=100.0,
                ),
                "AAPL": _FakeOptionsTicker(
                    options=[],  # graceful unavailable
                    spot_price=100.0,
                ),
                "BOOM": RuntimeError("ticker constructor failed"),
            }
        )

        results = self.module.fetch_options_many(
            tickers=["GOOGL", "AAPL", "BOOM"],
            output_dir=self.output_dir,
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(len(results), 3)
        by_ticker = {r["ticker"]: r for r in results}

        self.assertIsNotNone(by_ticker["GOOGL"]["implied_move_pct"])
        self.assertEqual(by_ticker["AAPL"].get("status"), "unavailable")
        self.assertEqual(by_ticker["BOOM"].get("status"), "unavailable")

        for tkr in ("GOOGL", "AAPL", "BOOM"):
            out = self.output_dir / f"{tkr}.json"
            self.assertTrue(out.exists(), f"{tkr}.json missing in output_dir")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["ticker"], tkr)
            self.assertIn("_sanitization", payload)


class OptionsFetcherNearestExpiryTests(OptionsFetcherTestBase):
    """Test 9: when multiple expiries are listed, the nearest future one wins."""

    def test_nearest_expiry_is_picked(self) -> None:
        # today = 2026-05-07
        # candidates: 2026-05-02 (past — skip), 2026-05-09 (D-2), 2026-05-16 (D-9)
        past = "2026-05-02"
        soon = "2026-05-09"
        later = "2026-05-16"
        calls = [_row(100, 2.0)]
        puts = [_row(100, 2.0)]
        yf = _FakeYFinance(
            {
                "MULTI": _FakeOptionsTicker(
                    options=[past, soon, later],
                    chain_by_expiry={
                        soon: _FakeChain(calls=calls, puts=puts),
                        later: _FakeChain(calls=calls, puts=puts),
                    },
                    spot_price=100.0,
                )
            }
        )

        record = self.module.fetch_options(
            ticker="MULTI",
            yf_module=yf,
            timeout=5,
            today_date=self.today_iso,
        )

        self.assertEqual(record["nearest_expiry"], soon)
        self.assertEqual(record["expiry_offset_days"], 2)


class OptionsFetcherModuleSurfaceTests(unittest.TestCase):
    """Sanity: the module exposes the expected surface."""

    def test_module_exposes_fetch_options_and_fetch_options_many(self) -> None:
        module = _load_options_fetcher()
        self.assertTrue(hasattr(module, "fetch_options"))
        self.assertTrue(callable(module.fetch_options))
        self.assertTrue(hasattr(module, "fetch_options_many"))
        self.assertTrue(callable(module.fetch_options_many))
        # CLAUDE.md §12: collector must wire prompt-injection sanitizer.
        self.assertTrue(hasattr(module, "sanitize_record"))
        self.assertTrue(callable(module.sanitize_record))


class OptionsFetcherNoYFinanceTests(OptionsFetcherTestBase):
    """Test 10: yfinance module unavailable → graceful unavailable record.

    Simulates "yfinance not installed" by temporarily monkey-patching the
    module-level default to None and passing yf_module=None. Even with no
    yfinance available, no exception escapes — the record degrades to
    ``status="unavailable"``.
    """

    def test_no_yfinance_module_returns_unavailable(self) -> None:
        original_default = getattr(self.module, "_yf_default", None)
        self.module._yf_default = None
        try:
            record = self.module.fetch_options(
                ticker="ANY",
                yf_module=None,
                timeout=5,
                today_date=self.today_iso,
            )
        finally:
            self.module._yf_default = original_default

        self.assertEqual(record.get("status"), "unavailable")
        self.assertIn("error", record)
        self.assertIn("_sanitization", record)


if __name__ == "__main__":
    unittest.main()
