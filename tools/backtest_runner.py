"""Backtest harness CLI entrypoint.

Runs the Stock Analysis Agent pipeline at historical as-of dates so we can
measure whether outputs (e.g. R/R Score) have predictive power for forward
returns.

This is the Task 1.1 scaffold: the CLI accepts ``--cohort`` and an
optional ``--as-of`` date, validates them, and either prints the parsed
arguments (``--dry-run``) or exits with a stub message. The full cohort
runner lands in Chunk 3.

Usage examples
--------------

Dry-run a single as-of date::

    python tools/backtest_runner.py --cohort smoke --as-of 2025-03-31 --dry-run

Stub invocation (exits 1 until Chunk 3 lands)::

    python tools/backtest_runner.py --cohort smoke

Exit codes
----------
- ``0``: dry-run completed; parsed arguments printed as JSON to stdout.
- ``1``: cohort runner stub (Chunk 3 not yet implemented).
- ``2``: argparse validation error (bad/missing flag, future as-of date).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections.abc import Sequence

_STUB_NOT_IMPLEMENTED = "Cohort runner not yet implemented (Chunk 3)."


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
            "Run the Stock Analysis Agent pipeline at a historical as-of "
            "date for backtesting. Cohort execution is implemented in "
            "Chunk 3; this entrypoint currently supports --dry-run only."
        ),
    )
    parser.add_argument(
        "--cohort",
        required=True,
        help="Cohort manifest id (resolved by Chunk 3 cohort loader).",
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=_parse_iso_date,
        default=None,
        help=(
            "Optional as-of date (YYYY-MM-DD). Used for direct testing "
            "before Chunk 3 cohort manifests can supply it."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print parsed arguments as JSON and exit without running.",
    )
    return parser


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

    payload = {
        "cohort": args.cohort,
        "as_of": args.as_of.isoformat() if args.as_of is not None else None,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(payload))
        return 0

    print(_STUB_NOT_IMPLEMENTED, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
