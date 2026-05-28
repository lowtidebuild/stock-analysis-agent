"""Ticker forward-price cache for backtest outcome computation.

The benchmark cache stores market index closes once per cohort. This module
does the same for per-ticker forward price windows used by
``OutcomeComputer`` so repeated ``outcomes`` runs do not need to call
yfinance again when the same ticker/window has already been fetched.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from dataclasses import asdict, dataclass
from typing import Any


TICKER_PRICE_CACHE_SCHEMA_VERSION = "backtest-ticker-price-cache-v1"


class TickerPriceCacheError(RuntimeError):
    """Raised when the ticker price cache is malformed or mismatched."""


@dataclass(frozen=True)
class TickerPriceCacheEvent:
    status: str
    ticker: str
    market: str
    window_start: str
    window_end: str
    path: str
    rows: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class TickerPriceCacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    refreshes: int = 0
    mismatches: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


CacheKey = tuple[str, str, _dt.date, _dt.date]


def load_ticker_price_cache(path: pathlib.Path) -> "TickerPriceCache":
    """Load a JSONL ticker price cache, returning an empty cache if missing."""

    cache = TickerPriceCache(path)
    cache.load()
    return cache


class TickerPriceCache:
    """Small JSONL-backed cache keyed by ticker, market, and date window."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self._records: dict[CacheKey, dict[_dt.date, float]] = {}
        self.stats = TickerPriceCacheStats()
        self.last_event: TickerPriceCacheEvent | None = None

    def load(self) -> None:
        if not self.path.exists():
            return
        if not self.path.is_file():
            raise TickerPriceCacheError(f"ticker price cache is not a file: {self.path}")

        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                record = self._parse_record(line=line, lineno=lineno)
                key = self._key(
                    ticker=record["ticker"],
                    market=record["market"],
                    start=record["start_date"],
                    end=record["end_date"],
                )
                if key in self._records:
                    raise TickerPriceCacheError(
                        f"line {lineno} of {self.path} duplicates "
                        f"ticker={key[0]!r} market={key[1]!r} "
                        f"window={key[2].isoformat()}..{key[3].isoformat()}"
                    )
                self._records[key] = record["prices"]

    def get(
        self,
        *,
        ticker: str,
        market: str,
        start: _dt.date,
        end: _dt.date,
    ) -> dict[_dt.date, float] | None:
        key = self._key(ticker=ticker, market=market, start=start, end=end)
        path = str(self.path)
        if key in self._records:
            prices = dict(self._records[key])
            self.stats.hits += 1
            self.last_event = TickerPriceCacheEvent(
                status="hit",
                ticker=key[0],
                market=key[1],
                window_start=key[2].isoformat(),
                window_end=key[3].isoformat(),
                path=path,
                rows=len(prices),
            )
            return prices

        windows = [
            cached_key
            for cached_key in self._records
            if cached_key[0] == key[0] and cached_key[1] == key[1]
        ]
        if windows:
            self.stats.mismatches += 1
            available = ", ".join(
                f"{cached_start.isoformat()}..{cached_end.isoformat()}"
                for _ticker, _market, cached_start, cached_end in sorted(windows)
            )
            self.last_event = TickerPriceCacheEvent(
                status="mismatch",
                ticker=key[0],
                market=key[1],
                window_start=key[2].isoformat(),
                window_end=key[3].isoformat(),
                path=path,
                reason=f"available windows: {available}",
            )
            raise TickerPriceCacheError(
                "ticker price cache window mismatch for "
                f"{key[0]} {key[1]}: requested {key[2].isoformat()}..{key[3].isoformat()}, "
                f"available {available}. Refresh the ticker price cache or use "
                "a cache built for the same benchmark/outcome window."
            )

        self.stats.misses += 1
        self.last_event = TickerPriceCacheEvent(
            status="miss",
            ticker=key[0],
            market=key[1],
            window_start=key[2].isoformat(),
            window_end=key[3].isoformat(),
            path=path,
            reason="no matching ticker/market entry",
        )
        return None

    def record_refresh(
        self,
        *,
        ticker: str,
        market: str,
        start: _dt.date,
        end: _dt.date,
    ) -> None:
        key = self._key(ticker=ticker, market=market, start=start, end=end)
        self.stats.refreshes += 1
        self.last_event = TickerPriceCacheEvent(
            status="refresh",
            ticker=key[0],
            market=key[1],
            window_start=key[2].isoformat(),
            window_end=key[3].isoformat(),
            path=str(self.path),
        )

    def put(
        self,
        *,
        ticker: str,
        market: str,
        start: _dt.date,
        end: _dt.date,
        prices: dict[_dt.date, float],
    ) -> None:
        if not prices:
            return
        key = self._key(ticker=ticker, market=market, start=start, end=end)
        self._records[key] = dict(sorted(prices.items()))
        self.stats.writes += 1
        self.last_event = TickerPriceCacheEvent(
            status="write",
            ticker=key[0],
            market=key[1],
            window_start=key[2].isoformat(),
            window_end=key[3].isoformat(),
            path=str(self.path),
            rows=len(prices),
        )
        self._write_all()

    def stats_dict(self) -> dict[str, int]:
        return self.stats.to_dict()

    def _write_all(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            for key in sorted(self._records):
                fh.write(json.dumps(self._record_for_key(key), sort_keys=True) + "\n")
        os.replace(tmp_path, self.path)

    def _record_for_key(self, key: CacheKey) -> dict[str, Any]:
        ticker, market, start, end = key
        prices = self._records[key]
        return {
            "schema_version": TICKER_PRICE_CACHE_SCHEMA_VERSION,
            "ticker": ticker,
            "market": market,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "cached_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "row_count": len(prices),
            "prices": [
                {"date": date.isoformat(), "close": close}
                for date, close in sorted(prices.items())
            ],
        }

    def _parse_record(self, *, line: str, lineno: int) -> dict[str, Any]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TickerPriceCacheError(
                f"failed to parse JSON on line {lineno} of {self.path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise TickerPriceCacheError(f"line {lineno} of {self.path} is not a JSON object")
        if payload.get("schema_version") != TICKER_PRICE_CACHE_SCHEMA_VERSION:
            raise TickerPriceCacheError(
                f"line {lineno} of {self.path} has unsupported schema_version="
                f"{payload.get('schema_version')!r}"
            )

        ticker = self._require_string(payload, "ticker", lineno)
        market = self._require_string(payload, "market", lineno)
        start = self._require_date(payload, "start_date", lineno)
        end = self._require_date(payload, "end_date", lineno)
        if end < start:
            raise TickerPriceCacheError(
                f"line {lineno} of {self.path} has end_date before start_date"
            )
        prices_raw = payload.get("prices")
        if not isinstance(prices_raw, list):
            raise TickerPriceCacheError(f"line {lineno} of {self.path} has non-list prices")

        prices: dict[_dt.date, float] = {}
        for index, item in enumerate(prices_raw):
            if not isinstance(item, dict):
                raise TickerPriceCacheError(
                    f"line {lineno} of {self.path} prices[{index}] is not an object"
                )
            try:
                date = _dt.date.fromisoformat(item["date"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TickerPriceCacheError(
                    f"line {lineno} of {self.path} prices[{index}] has invalid date"
                ) from exc
            try:
                close = float(item["close"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TickerPriceCacheError(
                    f"line {lineno} of {self.path} prices[{index}] has invalid close"
                ) from exc
            if date in prices:
                raise TickerPriceCacheError(
                    f"line {lineno} of {self.path} duplicates price date {date.isoformat()}"
                )
            prices[date] = close

        return {
            "ticker": ticker,
            "market": market,
            "start_date": start,
            "end_date": end,
            "prices": prices,
        }

    def _require_string(self, payload: dict[str, Any], field: str, lineno: int) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TickerPriceCacheError(
                f"line {lineno} of {self.path} missing string field {field!r}"
            )
        return value.strip().upper()

    def _require_date(self, payload: dict[str, Any], field: str, lineno: int) -> _dt.date:
        value = payload.get(field)
        try:
            return _dt.date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise TickerPriceCacheError(
                f"line {lineno} of {self.path} has invalid {field}={value!r}"
            ) from exc

    @staticmethod
    def _key(*, ticker: str, market: str, start: _dt.date, end: _dt.date) -> CacheKey:
        if end < start:
            raise TickerPriceCacheError("ticker price cache end date is before start date")
        return (ticker.strip().upper(), market.strip().upper(), start, end)


__all__ = [
    "TickerPriceCache",
    "TickerPriceCacheError",
    "TickerPriceCacheEvent",
    "TickerPriceCacheStats",
    "TICKER_PRICE_CACHE_SCHEMA_VERSION",
    "load_ticker_price_cache",
]
