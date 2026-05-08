"""Backtest harness CLI entrypoint.

Runs the Stock Analysis Agent pipeline at historical as-of dates so we can
measure whether outputs (e.g. R/R Score) have predictive power for forward
returns.

The CLI loads a cohort manifest (validated by
``tools.backtest.cohort_manifest``) and dispatches the
:class:`tools.backtest.batch_runner.BatchRunner` for the data-collection
phase: yfinance OHLC + statements per ticker, DART disclosures for
Korean tickers, and a single per-cohort FRED macro snapshot.

Usage examples
--------------

Dry-run a single as-of date::

    python tools/backtest_runner.py --cohort smoke --as-of 2025-03-31 --dry-run

Run a cohort end-to-end (data collection only — analyst integration
lands in Chunk 6)::

    python tools/backtest_runner.py --cohort smoke

Exit codes
----------
- ``0``: dry-run completed (parsed args printed) **or** cohort run
  finished and ``state.json`` was persisted.
- ``1``: cohort runner raised :class:`BatchRunnerError` (cohort-level
  fatal — e.g. ``state.json`` mismatch with the manifest).
- ``2``: argparse validation error (bad/missing flag, future as-of
  date), unknown cohort manifest, or ``--as-of`` mismatch with
  ``manifest.as_of``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from collections.abc import Sequence

# Make ``tools.*`` importable when this file is executed directly
# (``python tools/backtest_runner.py``) — argparse-only invocations
# previously did not need this because the stub had no inter-package
# imports.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.backtest.batch_runner import (  # noqa: E402
    BatchRunner,
    BatchRunnerError,
    TickerRunStatus,
)
from tools.backtest.cohort_manifest import (  # noqa: E402
    CohortManifestError,
    cohort_manifest_path,
    load_cohort,
)


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backtest_runner",
        description=(
            "Run the Stock Analysis Agent backtest harness for a cohort "
            "manifest. The data-collection phase is implemented; analyst "
            "integration lands in Chunk 6."
        ),
    )
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
        type=int,
        default=5,
        help="Maximum concurrent ticker fetches (default: 5).",
    )
    return parser


def _run_cohort(args: argparse.Namespace) -> int:
    """Resolve manifest, dispatch BatchRunner, print summary."""
    try:
        manifest_path = cohort_manifest_path(args.cohort)
    except CohortManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        manifest = load_cohort(manifest_path)
    except CohortManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
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

    # Tally per-status counts for the summary line.
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.as_of is not None:
        today = _dt.date.today()
        if args.as_of > today:
            parser.error(
                f"--as-of {args.as_of.isoformat()} is in the future "
                f"(today is {today.isoformat()})."
            )

    if args.dry_run:
        payload = {
            "cohort": args.cohort,
            "as_of": args.as_of.isoformat() if args.as_of is not None else None,
            "dry_run": args.dry_run,
        }
        print(json.dumps(payload))
        return 0

    return _run_cohort(args)


if __name__ == "__main__":
    raise SystemExit(main())
