"""Backtest harness CLI entrypoint.

Runs the Stock Analysis Agent pipeline at historical as-of dates so we can
measure whether outputs (e.g. R/R Score) have predictive power for forward
returns.

The CLI is structured as four subcommands:

``collect``
    Run :class:`tools.backtest.batch_runner.BatchRunner` for a cohort
    manifest — yfinance OHLC + statements per ticker, DART disclosures
    for Korean tickers, and a single per-cohort FRED macro snapshot.
``outcomes``
    Compute forward-return ``_outcome.json`` files for every ticker run
    in a cohort, using
    :class:`tools.backtest.outcome_computer.OutcomeComputer`.
``aggregate``
    Walk the cohort tree, join each ticker's ``_outcome.json`` with its
    ``analysis-result.json`` (best-effort), and write a single
    ``results.jsonl`` at the cohort root via
    :func:`tools.backtest.cohort_aggregator.aggregate_and_write`.
``all``
    Run ``collect`` → ``outcomes`` → ``aggregate`` sequentially. Aborts
    the chain if any step exits non-zero.

A backwards-compat shim accepts the *old* CLI shape — ``python
tools/backtest_runner.py --cohort smoke ...`` — and routes it to
``collect`` with a deprecation hint on stderr.

Usage examples
--------------

Dry-run a single as-of date::

    python tools/backtest_runner.py collect --cohort smoke --as-of 2025-03-31 --dry-run

Run data collection end-to-end::

    python tools/backtest_runner.py collect --cohort smoke

Compute outcomes for a cohort whose data is already on disk::

    python tools/backtest_runner.py outcomes --cohort smoke

Aggregate outcomes + analysis into ``results.jsonl``::

    python tools/backtest_runner.py aggregate --cohort smoke

Do all three in one shot::

    python tools/backtest_runner.py all --cohort smoke

Exit codes
----------
- ``0``: subcommand completed successfully (or dry-run printed and
  exited).
- ``1``: ``collect`` raised :class:`BatchRunnerError`, or one or more
  tickers failed during ``outcomes``.
- ``2``: argparse validation error (bad/missing flag, future as-of date),
  unknown cohort manifest, ``--as-of`` mismatch with manifest, or
  ``outcomes`` could not locate a benchmark cache (and ``--allow-fixture``
  was not set).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from collections.abc import Sequence

# Make ``tools.*`` importable when this file is executed directly
# (``python tools/backtest_runner.py``).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.backtest.batch_runner import (  # noqa: E402
    BatchRunner,
    BatchRunnerError,
    TickerRunStatus,
)
from tools.backtest.benchmark_cache import (  # noqa: E402
    BenchmarkCacheError,
    load_benchmark_cache,
)
from tools.backtest.cohort_aggregator import aggregate_and_write  # noqa: E402
from tools.backtest.cohort_manifest import (  # noqa: E402
    CohortManifest,
    CohortManifestError,
    cohort_manifest_path,
    load_cohort,
)
from tools.backtest.outcome_computer import (  # noqa: E402
    ForwardPriceUnavailable,
    OutcomeComputer,
    OutcomeComputerError,
)
from tools.paths import backtest_path  # noqa: E402


# ---------------------------------------------------------------------------
# Default benchmark cache locations
# ---------------------------------------------------------------------------


_DEFAULT_BENCH_CACHE = (
    _REPO_ROOT / "evals" / "backtest" / "data" / "benchmark-prices.jsonl"
)
_FIXTURE_BENCH_CACHE = (
    _REPO_ROOT / "evals" / "backtest" / "data" / "benchmark-prices-fixture.jsonl"
)


# ---------------------------------------------------------------------------
# Argparse helpers
# ---------------------------------------------------------------------------


def _positive_int(value: str) -> int:
    """Parse a positive integer for argparse.

    Bounces invalid input at the boundary so callers see a clean
    argparse error (exit 2) instead of a Python traceback bubbling out
    of ``BatchRunner.__init__``.
    """
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer (got {value!r})"
        ) from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(
            f"must be >= 1 (got {parsed})"
        )
    return parsed


def _parse_iso_date(value: str) -> _dt.date:
    """Parse a strict ``YYYY-MM-DD`` date string.

    Raises ``argparse.ArgumentTypeError`` on any deviation (wrong
    separator, wrong field widths, invalid calendar date).
    """
    try:
        parsed = _dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--as-of must be YYYY-MM-DD (got {value!r}): {exc}"
        ) from exc
    return parsed


def _add_collect_args(parser: argparse.ArgumentParser) -> None:
    """Register ``collect`` (and ``all``) shared arguments on ``parser``."""
    parser.add_argument(
        "--cohort",
        required=True,
        help="Cohort manifest id (resolved under evals/backtest/cohorts/).",
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=_parse_iso_date,
        default=None,
        help=(
            "Optional explicit as-of date (YYYY-MM-DD). When provided it "
            "must match the manifest's as_of; otherwise the run is "
            "rejected. The manifest is the source of truth."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print parsed arguments as JSON and exit without running.",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=5,
        help="Maximum concurrent ticker fetches (default: 5).",
    )


def _add_outcomes_args(parser: argparse.ArgumentParser) -> None:
    """Register ``outcomes`` (and ``all``) shared arguments on ``parser``."""
    parser.add_argument(
        "--benchmark-cache",
        dest="benchmark_cache",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to the benchmark-prices JSONL file. Defaults to "
            "evals/backtest/data/benchmark-prices.jsonl."
        ),
    )
    parser.add_argument(
        "--allow-fixture",
        dest="allow_fixture",
        action="store_true",
        help=(
            "Fall back to the small fixture cache "
            "(evals/backtest/data/benchmark-prices-fixture.jsonl) when "
            "the real cache is missing. Tests/dev only."
        ),
    )
    parser.add_argument(
        "--prefer-qqq",
        dest="prefer_qqq",
        action="store_true",
        help="Use QQQ instead of SPY as the US benchmark.",
    )
    skip_group = parser.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help=(
            "Skip ticker dirs that already have an _outcome.json (default)."
        ),
    )
    skip_group.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Recompute outcomes even when _outcome.json already exists.",
    )


def _add_aggregate_args(parser: argparse.ArgumentParser) -> None:
    """Register ``aggregate`` (and ``all``) shared arguments on ``parser``."""
    parser.add_argument(
        "--cohort",
        required=True,
        help="Cohort manifest id (resolved under evals/backtest/cohorts/).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backtest_runner",
        description=(
            "Run the Stock Analysis Agent backtest harness. Subcommands: "
            "collect (data), outcomes (forward returns), aggregate "
            "(results.jsonl), all (chain). The legacy `--cohort X` shape "
            "is still accepted and routes to `collect`."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect ---------------------------------------------------------------
    collect_parser = subparsers.add_parser(
        "collect",
        help="Run BatchRunner data collection (yfinance + DART + FRED).",
    )
    _add_collect_args(collect_parser)

    # outcomes --------------------------------------------------------------
    outcomes_parser = subparsers.add_parser(
        "outcomes",
        help="Compute forward-return _outcome.json per ticker dir.",
    )
    outcomes_parser.add_argument(
        "--cohort",
        required=True,
        help="Cohort manifest id (resolved under evals/backtest/cohorts/).",
    )
    _add_outcomes_args(outcomes_parser)

    # aggregate -------------------------------------------------------------
    aggregate_parser = subparsers.add_parser(
        "aggregate",
        help="Join outcomes + analysis into cohort results.jsonl.",
    )
    _add_aggregate_args(aggregate_parser)

    # all -------------------------------------------------------------------
    all_parser = subparsers.add_parser(
        "all",
        help="Run collect → outcomes → aggregate sequentially.",
    )
    _add_collect_args(all_parser)
    _add_outcomes_args(all_parser)

    return parser


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _load_manifest_or_exit(
    cohort_id: str,
    *,
    severity: str = "ERROR",
) -> CohortManifest | None:
    """Resolve and load a cohort manifest.

    Returns the manifest on success, or ``None`` if it could not be
    resolved/loaded — the caller decides whether that is fatal.

    ``severity`` controls the stderr prefix: ``"ERROR"`` (caller treats
    missing manifest as fatal — used by ``collect``) vs ``"WARN"``
    (caller treats it as best-effort — used by ``outcomes`` /
    ``aggregate``, where the manifest only refines an otherwise-derived
    cohort layout). Avoids the prior misleading "ERROR ... cohort=smoke
    rows=N exit 0" message at 11pm.
    """
    try:
        manifest_path = cohort_manifest_path(cohort_id)
    except CohortManifestError as exc:
        print(f"{severity}: {exc}", file=sys.stderr)
        return None

    try:
        return load_cohort(manifest_path)
    except CohortManifestError as exc:
        print(f"{severity}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# collect subcommand
# ---------------------------------------------------------------------------


def _run_collect(args: argparse.Namespace) -> int:
    """Resolve manifest, dispatch BatchRunner, print summary."""
    if args.dry_run:
        payload = {
            "cohort": args.cohort,
            "as_of": args.as_of.isoformat() if args.as_of is not None else None,
            "dry_run": True,
        }
        print(json.dumps(payload))
        return 0

    manifest = _load_manifest_or_exit(args.cohort)
    if manifest is None:
        return 2

    if args.as_of is not None and args.as_of != manifest.as_of:
        print(
            f"ERROR: --as-of {args.as_of.isoformat()} does not match "
            f"manifest.as_of {manifest.as_of.isoformat()} (the manifest "
            f"is the source of truth).",
            file=sys.stderr,
        )
        return 2

    try:
        runner = BatchRunner(manifest=manifest, max_workers=args.max_workers)
        state = runner.run()
    except BatchRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    counts: dict[str, int] = {status.value: 0 for status in TickerRunStatus}
    for record in state.runs.values():
        counts[record.status.value] += 1

    print(
        "cohort={cohort} as_of={as_of} done={done} failed={failed} "
        "skipped={skipped} pending={pending} running={running} "
        "total_bytes={bytes}".format(
            cohort=manifest.cohort_id,
            as_of=manifest.as_of.isoformat(),
            done=counts[TickerRunStatus.DONE.value],
            failed=counts[TickerRunStatus.FAILED.value],
            skipped=counts[TickerRunStatus.SKIPPED.value],
            pending=counts[TickerRunStatus.PENDING.value],
            running=counts[TickerRunStatus.RUNNING.value],
            bytes=state.total_bytes_written,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# outcomes subcommand
# ---------------------------------------------------------------------------


def _resolve_benchmark_cache_path(
    requested: pathlib.Path | None,
    *,
    allow_fixture: bool,
) -> pathlib.Path | None:
    """Resolve which benchmark JSONL to load.

    Priority:
    1. Explicit ``--benchmark-cache PATH`` if it exists.
    2. Default real cache (``benchmark-prices.jsonl``) if it exists.
    3. Fixture cache (``benchmark-prices-fixture.jsonl``) ONLY when
       ``--allow-fixture`` is set.

    Returns the chosen path, or ``None`` if no usable cache could be
    located.
    """
    candidate = requested if requested is not None else _DEFAULT_BENCH_CACHE
    if candidate.is_file():
        return candidate
    if allow_fixture and _FIXTURE_BENCH_CACHE.is_file():
        return _FIXTURE_BENCH_CACHE
    return None


def _read_meta(meta_path: pathlib.Path) -> dict | None:
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_outcomes(args: argparse.Namespace) -> int:
    """Compute forward-return outcomes for every ticker dir in the cohort."""
    cache_path = _resolve_benchmark_cache_path(
        args.benchmark_cache, allow_fixture=args.allow_fixture
    )
    if cache_path is None:
        attempted = (
            args.benchmark_cache if args.benchmark_cache is not None
            else _DEFAULT_BENCH_CACHE
        )
        print(
            f"ERROR: benchmark cache not found at {attempted}.\n"
            "Build it with `python evals/backtest/scripts/cache-benchmarks.py`, "
            "or pass --allow-fixture to use the small shipped fixture "
            "(tests/dev only).",
            file=sys.stderr,
        )
        return 2

    try:
        cache = load_benchmark_cache(cache_path)
    except BenchmarkCacheError as exc:
        print(f"ERROR: failed to load benchmark cache: {exc}", file=sys.stderr)
        return 2

    # Manifest is best-effort — used to map ticker → market when meta
    # files are missing the field.
    manifest = _load_manifest_or_exit(args.cohort, severity="WARN")
    manifest_market: dict[str, str] = {}
    if manifest is not None:
        for entry in manifest.tickers:
            manifest_market[entry.ticker] = entry.market

    cohort_root = backtest_path("cohorts", args.cohort)
    runs_dir = cohort_root / "runs"
    if not runs_dir.is_dir():
        print(
            f"cohort={args.cohort} done=0 failed=0 skipped=0 "
            f"(no runs/ directory at {runs_dir})"
        )
        return 0

    computer = OutcomeComputer(benchmark_cache=cache)

    done = failed = skipped = 0
    for ticker_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        ticker = ticker_dir.name
        outcome_path = ticker_dir / "_outcome.json"
        if args.skip_existing and outcome_path.exists():
            skipped += 1
            continue

        meta = _read_meta(ticker_dir / "_backtest-meta.json")
        if meta is None:
            print(
                f"WARN: {ticker_dir} has no _backtest-meta.json — skipping",
                file=sys.stderr,
            )
            failed += 1
            continue

        as_of_raw = meta.get("as_of")
        try:
            as_of = _dt.date.fromisoformat(as_of_raw) if isinstance(as_of_raw, str) else None
        except ValueError:
            as_of = None
        if as_of is None:
            print(
                f"WARN: {ticker_dir} has invalid as_of in meta — skipping",
                file=sys.stderr,
            )
            failed += 1
            continue

            # Market resolution. We must NOT silently default to "US" — a KR
        # ticker would then get SPY as the benchmark and produce a wrong
        # excess_return (the project's "blank > wrong number" principle).
        # `BacktestContext.write_meta()` does not currently persist
        # market, so the manifest is the only authoritative source.
        manifest_value = manifest_market.get(ticker)
        meta_value = meta.get("market") if isinstance(meta.get("market"), str) else None
        market = manifest_value or meta_value
        if market is None:
            print(
                f"FAIL: {ticker} ({as_of.isoformat()}): cannot resolve market — "
                f"manifest missing or ticker not listed AND _backtest-meta.json "
                f"has no `market` field. Add the ticker to the manifest or "
                f"pass --benchmark-cache that includes the right index.",
                file=sys.stderr,
            )
            failed += 1
            continue
        if market not in ("US", "KR"):
            print(
                f"FAIL: {ticker} ({as_of.isoformat()}): unsupported market={market!r}",
                file=sys.stderr,
            )
            failed += 1
            continue

        try:
            outcome = computer.compute(
                ticker=ticker,
                market=market,  # type: ignore[arg-type]
                as_of=as_of,
                prefer_qqq=args.prefer_qqq,
            )
        except ForwardPriceUnavailable as exc:
            print(f"FAIL: {ticker} ({as_of.isoformat()}): {exc}", file=sys.stderr)
            failed += 1
            continue
        except OutcomeComputerError as exc:
            print(f"FAIL: {ticker} ({as_of.isoformat()}): {exc}", file=sys.stderr)
            failed += 1
            continue
        except Exception as exc:  # pragma: no cover — defensive
            print(
                f"FAIL: {ticker} ({as_of.isoformat()}): unexpected {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failed += 1
            continue

        computer.write_outcome(ticker_run_dir=ticker_dir, outcome=outcome)
        done += 1

    print(
        f"cohort={args.cohort} done={done} failed={failed} skipped={skipped}"
    )
    return 1 if failed > 0 else 0


# ---------------------------------------------------------------------------
# aggregate subcommand
# ---------------------------------------------------------------------------


def _run_aggregate(args: argparse.Namespace) -> int:
    """Aggregate cohort outcomes + analysis into ``results.jsonl``."""
    # Manifest is best-effort: it provides the source of truth for
    # (ticker, market, as_of), but aggregate also tolerates orphan run
    # dirs anchored only on _backtest-meta.json or _outcome.json.
    manifest = _load_manifest_or_exit(args.cohort, severity="WARN")
    out_path = aggregate_and_write(cohort_id=args.cohort, manifest=manifest)

    if out_path.exists():
        text = out_path.read_text(encoding="utf-8")
        rows = 0 if not text.strip() else len(text.strip().split("\n"))
    else:
        rows = 0

    print(f"cohort={args.cohort} rows={rows} output={out_path}")
    return 0


# ---------------------------------------------------------------------------
# all subcommand
# ---------------------------------------------------------------------------


def _run_all(args: argparse.Namespace) -> int:
    """Run collect → outcomes → aggregate sequentially.

    Aborts the chain if any step exits non-zero. ``--dry-run`` is
    honored as the conventional "no externally-observable side effects"
    contract: collect prints its dry-run JSON and the chain stops there
    (no real yfinance fetches, no results.jsonl write).
    """
    rc = _run_collect(args)
    if rc != 0:
        return rc
    if args.dry_run:
        # Dry-run contract: stop after collect's JSON preview. Running
        # outcomes (which calls yfinance) and aggregate (which writes
        # results.jsonl) under --dry-run would surprise operators.
        return 0

    rc = _run_outcomes(args)
    if rc != 0:
        return rc

    rc = _run_aggregate(args)
    return rc


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_LEGACY_FLAGS = {"--cohort", "--as-of", "--dry-run", "--max-workers"}


def _is_legacy_invocation(argv: Sequence[str]) -> bool:
    """Return True if ``argv`` looks like the pre-Task-6.1 CLI shape.

    Heuristic: no positional subcommand AND the first token starts with
    ``--``. We additionally check that the first flag is one of the
    documented legacy flags so that ``--help``/``-h`` is still routed
    through argparse normally.
    """
    if not argv:
        return False
    first = argv[0]
    if not first.startswith("--"):
        return False
    if first in {"--help", "-h"}:
        return False
    return first in _LEGACY_FLAGS


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)

    if _is_legacy_invocation(argv):
        print(
            "WARN: the bare `--cohort X` CLI shape is deprecated; "
            "use `backtest_runner collect --cohort X` instead. Routing "
            "this invocation to `collect` for backward compatibility.",
            file=sys.stderr,
        )
        argv = ["collect", *argv]

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Future-date guard applies to subcommands that accept --as-of.
    if getattr(args, "as_of", None) is not None:
        today = _dt.date.today()
        if args.as_of > today:
            parser.error(
                f"--as-of {args.as_of.isoformat()} is in the future "
                f"(today is {today.isoformat()})."
            )

    if args.command == "collect":
        return _run_collect(args)
    if args.command == "outcomes":
        return _run_outcomes(args)
    if args.command == "aggregate":
        return _run_aggregate(args)
    if args.command == "all":
        return _run_all(args)

    # argparse's required=True should make this unreachable.
    parser.error(f"unknown command: {args.command!r}")
    return 2  # pragma: no cover — argparse exits before reaching here


if __name__ == "__main__":
    raise SystemExit(main())
