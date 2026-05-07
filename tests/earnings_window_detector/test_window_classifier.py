"""Tests for the Phase F.1 earnings-window-detector (window-classifier.py).

The window-classifier is invoked at Workflow 1 entry to classify whether a
ticker is in a Mode E earnings window:

* ``preview`` — D-7 ~ D-1 (7 days before report through day-before)
* ``review``  — D ~ D+3   (report day through 3 days after)
* ``none``    — outside the window

Contract for the script:

* Programmatic surface (these tests):
  - ``classify_window(ticker, today_date, yf_module=None, timeout=30)`` returns
    one dict with the schema described below.
  - ``classify_windows(tickers, output_dir, today_date, yf_module=None,
    timeout=30)`` writes one JSON per ticker into ``output_dir``; returns a
    list of result dicts.

* Per-ticker JSON contains the keys::

      ticker, today_date, next_earnings_date, next_earnings_confirmed,
      days_until, window, override_mode, lookup_source, fallback_used,
      _sanitization

* Lookup precedence:
  1. ``yfinance.Ticker(t).calendar`` (dict-like with "Earnings Date")
  2. ``yfinance.Ticker(t).earnings_dates`` (DataFrame; pick next future date)
  3. Both fail → window="none", next_earnings_confirmed=False, fallback_used=True

* Sanitization block always present (CLAUDE.md §12 trust boundary).
* Per-ticker errors never raise (one bad ticker does not abort siblings).
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
CLASSIFIER_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "earnings-window-detector"
    / "scripts"
    / "window-classifier.py"
)


def _load_classifier():
    spec = importlib.util.spec_from_file_location(
        "window_classifier", CLASSIFIER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(
            f"failed to load window-classifier.py from {CLASSIFIER_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# yfinance test doubles
# ---------------------------------------------------------------------------


class _FakeTickerCalendar:
    """Mimics ``yfinance.Ticker(t)`` with controllable .calendar/.earnings_dates."""

    def __init__(
        self,
        calendar=None,
        earnings_dates=None,
        calendar_raises=None,
        earnings_dates_raises=None,
    ):
        self._calendar = calendar
        self._earnings_dates = earnings_dates
        self._calendar_raises = calendar_raises
        self._earnings_dates_raises = earnings_dates_raises

    @property
    def calendar(self):
        if self._calendar_raises is not None:
            raise self._calendar_raises
        return self._calendar

    @property
    def earnings_dates(self):
        if self._earnings_dates_raises is not None:
            raise self._earnings_dates_raises
        return self._earnings_dates


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
            return _FakeTickerCalendar(calendar={}, earnings_dates=None)
        return spec


# ---------------------------------------------------------------------------
# DataFrame-like double for earnings_dates
# ---------------------------------------------------------------------------


class _FakeIndex:
    """Iterable of datetimes (DatetimeIndex stand-in)."""

    def __init__(self, dates):
        self._dates = list(dates)

    def __iter__(self):
        return iter(self._dates)

    def __len__(self):
        return len(self._dates)


class _FakeEarningsDatesDF:
    """Mimics yfinance ``earnings_dates`` DataFrame.

    The real object is a pandas DataFrame with a DatetimeIndex (one row per
    quarter). The classifier only needs to enumerate index entries to find
    the next future date, so this stub exposes ``.index`` and ``.empty``.
    """

    def __init__(self, dates):
        self.index = _FakeIndex(dates)
        self.empty = len(dates) == 0


# ---------------------------------------------------------------------------
# Helpers to build a yfinance .calendar dict at a given offset from today
# ---------------------------------------------------------------------------


def _calendar_with_date(d):
    """Return a calendar dict shaped like yfinance returns."""
    return {"Earnings Date": [d]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class WindowClassifierTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="window_classifier_test_"))
        self.output_dir = self.tmp / "run" / "windows"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.module = _load_classifier()
        # Anchor today so date math is deterministic.
        self.today = date(2026, 5, 7)
        self.today_iso = self.today.isoformat()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class WindowClassifierPreviewTests(WindowClassifierTestBase):
    """Test 1: D-3 → window=preview (D-7..D-1 range)."""

    def test_three_days_until_classifies_as_preview(self) -> None:
        earnings = self.today + timedelta(days=3)  # D-3
        yf = _FakeYFinance(
            {"GOOGL": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="GOOGL",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["ticker"], "GOOGL")
        self.assertEqual(result["window"], "preview")
        self.assertEqual(result["days_until"], 3)
        self.assertTrue(result["next_earnings_confirmed"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["next_earnings_date"], earnings.isoformat())
        self.assertEqual(result["lookup_source"], "yfinance.Ticker.calendar")


class WindowClassifierReviewTodayTests(WindowClassifierTestBase):
    """Test 2: D-day → window=review (D..D+3 range)."""

    def test_today_is_earnings_day_classifies_as_review(self) -> None:
        earnings = self.today  # D-day
        yf = _FakeYFinance(
            {"AAPL": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="AAPL",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["window"], "review")
        self.assertEqual(result["days_until"], 0)
        self.assertTrue(result["next_earnings_confirmed"])


class WindowClassifierNoneFutureTests(WindowClassifierTestBase):
    """Test 3: D-30 → window=none (outside D-7..D+3)."""

    def test_thirty_days_until_classifies_as_none(self) -> None:
        earnings = self.today + timedelta(days=30)
        yf = _FakeYFinance(
            {"MSFT": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="MSFT",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["window"], "none")
        self.assertEqual(result["days_until"], 30)
        self.assertTrue(result["next_earnings_confirmed"])


class WindowClassifierReviewPastTests(WindowClassifierTestBase):
    """Test 4: D+1 (1 day ago) → window=review (within D..D+3)."""

    def test_one_day_ago_classifies_as_review(self) -> None:
        earnings = self.today - timedelta(days=1)  # D+1
        yf = _FakeYFinance(
            {"NVDA": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="NVDA",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["window"], "review")
        self.assertEqual(result["days_until"], -1)


class WindowClassifierNonePastTests(WindowClassifierTestBase):
    """Test 5: D+4 (4 days ago) → window=none (outside D..D+3)."""

    def test_four_days_ago_classifies_as_none(self) -> None:
        earnings = self.today - timedelta(days=4)  # D+4
        yf = _FakeYFinance(
            {"META": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="META",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["window"], "none")
        self.assertEqual(result["days_until"], -4)


class WindowClassifierFallbackToEarningsDatesTests(WindowClassifierTestBase):
    """Test 6: empty calendar → fallback to earnings_dates DataFrame."""

    def test_empty_calendar_falls_back_to_earnings_dates_df(self) -> None:
        future_earnings = self.today + timedelta(days=2)  # D-2 → preview
        far_past = self.today - timedelta(days=90)
        yf = _FakeYFinance(
            {
                "TSLA": _FakeTickerCalendar(
                    calendar={},  # empty calendar
                    earnings_dates=_FakeEarningsDatesDF(
                        # mix of past + future; classifier picks nearest future
                        [far_past, future_earnings, future_earnings + timedelta(days=90)]
                    ),
                )
            }
        )

        result = self.module.classify_window(
            ticker="TSLA",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["window"], "preview")
        self.assertEqual(result["days_until"], 2)
        self.assertEqual(
            result["next_earnings_date"], future_earnings.isoformat()
        )
        self.assertTrue(result["next_earnings_confirmed"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(
            result["lookup_source"], "yfinance.Ticker.earnings_dates"
        )


class WindowClassifierBothFailTests(WindowClassifierTestBase):
    """Test 7: both yfinance paths fail → window=none, confirmed=False, fallback_used=True."""

    def test_both_paths_fail_returns_none_with_fallback_flag(self) -> None:
        yf = _FakeYFinance(
            {
                "BADTKR": _FakeTickerCalendar(
                    calendar_raises=RuntimeError("calendar boom"),
                    earnings_dates_raises=RuntimeError("earnings_dates boom"),
                )
            }
        )

        result = self.module.classify_window(
            ticker="BADTKR",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["ticker"], "BADTKR")
        self.assertEqual(result["window"], "none")
        self.assertFalse(result["next_earnings_confirmed"])
        self.assertTrue(result["fallback_used"])
        self.assertIsNone(result["next_earnings_date"])
        self.assertIsNone(result["days_until"])
        self.assertIn("_sanitization", result)


class WindowClassifierSanitizationTests(WindowClassifierTestBase):
    """Test 8: sanitization block always present and well-formed."""

    def test_sanitization_block_present_on_success(self) -> None:
        earnings = self.today + timedelta(days=3)
        yf = _FakeYFinance(
            {"GOOGL": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="GOOGL",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertIn("_sanitization", result)
        san = result["_sanitization"]
        self.assertEqual(san["tool"], "tools/prompt_injection_filter.py")
        self.assertIn("version", san)
        self.assertIn("redactions", san)
        self.assertIn("findings", san)

    def test_sanitization_block_present_on_failure(self) -> None:
        yf = _FakeYFinance(
            {"BAD": _FakeTickerCalendar(
                calendar_raises=RuntimeError("boom"),
                earnings_dates_raises=RuntimeError("boom"),
            )}
        )

        result = self.module.classify_window(
            ticker="BAD",
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertIn("_sanitization", result)
        self.assertEqual(
            result["_sanitization"]["tool"], "tools/prompt_injection_filter.py"
        )


class WindowClassifierMultiTickerCliTests(WindowClassifierTestBase):
    """Test 9: classify_windows handles multiple tickers and writes per-ticker files."""

    def test_classify_windows_writes_one_file_per_ticker(self) -> None:
        earnings_g = self.today + timedelta(days=3)  # preview
        earnings_a = self.today - timedelta(days=10)  # none
        yf = _FakeYFinance(
            {
                "GOOGL": _FakeTickerCalendar(
                    calendar=_calendar_with_date(earnings_g)
                ),
                "AAPL": _FakeTickerCalendar(
                    calendar=_calendar_with_date(earnings_a)
                ),
                "BAD": _FakeTickerCalendar(
                    calendar_raises=RuntimeError("boom"),
                    earnings_dates_raises=RuntimeError("boom"),
                ),
            }
        )

        results = self.module.classify_windows(
            tickers=["GOOGL", "AAPL", "BAD"],
            output_dir=self.output_dir,
            today_date=self.today_iso,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(len(results), 3)
        by_ticker = {r["ticker"]: r for r in results}

        self.assertEqual(by_ticker["GOOGL"]["window"], "preview")
        self.assertEqual(by_ticker["AAPL"]["window"], "none")
        self.assertEqual(by_ticker["BAD"]["window"], "none")
        self.assertTrue(by_ticker["BAD"]["fallback_used"])

        # One file per ticker written.
        for tkr in ("GOOGL", "AAPL", "BAD"):
            out = self.output_dir / f"{tkr}.json"
            self.assertTrue(out.exists(), f"{tkr}.json missing in output_dir")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["ticker"], tkr)
            self.assertIn("_sanitization", payload)
            self.assertIn("window", payload)


class WindowClassifierModuleSurfaceTests(unittest.TestCase):
    """Sanity: the module exposes the expected surface."""

    def test_module_exposes_classify_window_and_classify_windows(self) -> None:
        module = _load_classifier()
        self.assertTrue(hasattr(module, "classify_window"))
        self.assertTrue(callable(module.classify_window))
        self.assertTrue(hasattr(module, "classify_windows"))
        self.assertTrue(callable(module.classify_windows))
        # CLAUDE.md §12: classifier must wire prompt-injection sanitizer.
        self.assertTrue(hasattr(module, "sanitize_record"))


class WindowClassifierDefaultTodayTests(WindowClassifierTestBase):
    """Test 10: omitted today_date defaults to UTC today."""

    def test_omitted_today_date_uses_utc_today(self) -> None:
        utc_today = datetime.now(timezone.utc).date()
        earnings = utc_today + timedelta(days=2)  # D-2 → preview
        yf = _FakeYFinance(
            {"AMZN": _FakeTickerCalendar(calendar=_calendar_with_date(earnings))}
        )

        result = self.module.classify_window(
            ticker="AMZN",
            today_date=None,
            yf_module=yf,
            timeout=5,
        )

        self.assertEqual(result["today_date"], utc_today.isoformat())
        self.assertEqual(result["window"], "preview")


if __name__ == "__main__":
    unittest.main()
