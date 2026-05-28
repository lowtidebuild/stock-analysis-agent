# 2026-05-28 Backtest Outcomes Cache Measurement

## Scope

- Cohort: `2025Q1`
- Tickers: 30 US tickers
- As-of: `2025-03-31`
- Benchmark cache: `evals/backtest/data/benchmark-prices.jsonl`
- Ticker price cache: `evals/backtest/data/ticker-prices/2025Q1-measurement.jsonl`
- Command mode: `tools/backtest_runner.py outcomes --no-skip-existing`

## Commands

```bash
/usr/bin/time -p python3 tools/backtest_runner.py outcomes \
  --cohort 2025Q1 \
  --no-skip-existing \
  --benchmark-cache evals/backtest/data/benchmark-prices.jsonl
```

```bash
/usr/bin/time -p python3 tools/backtest_runner.py outcomes \
  --cohort 2025Q1 \
  --no-skip-existing \
  --benchmark-cache evals/backtest/data/benchmark-prices.jsonl \
  --ticker-price-cache evals/backtest/data/ticker-prices/2025Q1-measurement.jsonl \
  --refresh-ticker-price-cache
```

```bash
/usr/bin/time -p python3 tools/backtest_runner.py outcomes \
  --cohort 2025Q1 \
  --no-skip-existing \
  --benchmark-cache evals/backtest/data/benchmark-prices.jsonl \
  --ticker-price-cache evals/backtest/data/ticker-prices/2025Q1-measurement.jsonl
```

## Results

| Run | Result | Ticker cache | Real time |
|---|---:|---|---:|
| baseline, no ticker cache | `done=30 failed=0 skipped=0` | hits `0`, misses `0`, writes `0` | `6.85s` |
| refresh/write cache | `done=30 failed=0 skipped=0` | hits `0`, misses `0`, writes `30`, refreshes `30` | `6.86s` |
| cache-hit rerun | `done=30 failed=0 skipped=0` | hits `30`, misses `0`, writes `0` | `0.05s` |

## Summary

- Cache-hit rerun reduced wall-clock time from `6.85s` to `0.05s`.
- Wall-clock reduction: about `99.3%`.
- Speedup: about `137x`.
- Ticker price network fetches for the repeated `outcomes` run were avoided for all 30 tickers, as shown by `ticker_cache_hits=30` and `ticker_cache_misses=0`.

## Cache Artifact

- Path: `evals/backtest/data/ticker-prices/2025Q1-measurement.jsonl`
- Size: `412K`
- Records: `30`
- Total price rows: `7,950`
- Per ticker rows: `265`
- Window: `2025-03-26` to `2026-04-15`
- Schema: `backtest-ticker-price-cache-v1`

## Notes

- Initial sandboxed smoke run failed DNS resolution for Yahoo Finance. The same smoke command succeeded after network access was allowed.
- The final cache-hit run writes cache status into each `_outcome.json` under `_backtest_meta.ticker_price_cache`.
