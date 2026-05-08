"""Historical data adapters for the backtest harness.

The backtest harness needs to fetch market data and financial statements
*as of* a historical date so we can replay the pipeline without leaking
future information. This module wraps the existing production fetchers
(under ``.claude/skills/financial-data-collector/scripts/``) and exposes
a clean Python surface the cohort runner (Chunk 3) will call.

The adapters intentionally subprocess-call the existing scripts rather
than importing them as modules. Three reasons:

1. **Production parity.** The Chunk 1+2 production pipeline already
   invokes these scripts as subprocesses (see ``CLAUDE.md`` Step 3 +
   Step 4). Using the same calling convention means the backtest path
   exercises the same code paths users hit in production — no risk of
   "works in tests, breaks in prod" because of import-time side effects.
2. **Process isolation.** yfinance keeps state on the ``Ticker`` object
   (rate-limit tokens, info cache). Spawning a fresh subprocess per
   ticker keeps backtest runs hermetic.
3. **Hyphenated filenames.** ``yfinance-collector.py`` is not a valid
   Python identifier, so importing it directly requires
   ``importlib.util`` ceremony anyway.

Currently exported
------------------

- :class:`YFinanceHistorical` — wraps yfinance-collector.py with
  ``--as-of`` enabled (Task 2.1, this file).

Future tasks (Chunk 2 follow-ups, NOT this file):

- ``FREDHistorical`` (Task 2.2) for FRED macro snapshots
- ``SECHistorical`` (Task 2.3) for SEC filings as-of
- ``DARTHistorical`` (Task 2.4) for KR filings as-of

TODO(integration-test): a live-network sanity check against AAPL with
``as_of=2025-01-15`` belongs in ``tests/financial_data_collector/
test_yfinance_as_of_flag.py`` under the ``INTEGRATION_TESTS=1`` gate. We
keep it opt-in so CI stays deterministic.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys
from typing import Any, Literal

from tools.paths import REPO_ROOT

_DEFAULT_SCRIPT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "financial-data-collector"
    / "scripts"
    / "yfinance-collector.py"
)
_DEFAULT_TIMEOUT_SECONDS = 60
_DEFAULT_BUNDLE = "standard"


class HistoricalFetchError(RuntimeError):
    """Raised when an as-of historical fetch fails.

    The exception message preserves the underlying script's stderr so
    callers (and the cohort runner) can surface diagnostics without
    re-running the subprocess.
    """


class YFinanceHistorical:
    """Subprocess-driven adapter for yfinance-collector.py with --as-of.

    Parameters
    ----------
    script_path:
        Optional override for the path to ``yfinance-collector.py``.
        Defaults to the repo's bundled script. Useful for tests.
    timeout_seconds:
        Wall-clock timeout for the subprocess. The script itself uses a
        per-call timeout (``--timeout``); this guards the *entire* run.
    """

    def __init__(
        self,
        *,
        script_path: pathlib.Path | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.script_path: pathlib.Path = (
            script_path if script_path is not None else _DEFAULT_SCRIPT_PATH
        )
        self.timeout_seconds: int = timeout_seconds

    def fetch(
        self,
        *,
        ticker: str,
        market: Literal["US", "KR"],
        as_of: _dt.date,
        output_path: pathlib.Path,
        bundle: str = _DEFAULT_BUNDLE,
    ) -> dict[str, Any]:
        """Fetch yfinance data as of ``as_of`` and return the parsed JSON.

        The subprocess is invoked exactly the way the production
        pipeline invokes it, with the addition of ``--as-of``. The
        script writes its result to ``output_path``; this method then
        reads, parses, and returns it.

        Parameters
        ----------
        ticker:
            Stock ticker (e.g. ``"AAPL"``, ``"005930"``).
        market:
            ``"US"`` or ``"KR"``.
        as_of:
            Historical anchor (no future leakage). The collector script
            rejects future dates with exit code 2.
        output_path:
            Where the script should write its JSON output. Parent dirs
            are created by the script.
        bundle:
            ``"minimum"`` or ``"standard"``. Defaults to ``"standard"``.

        Returns
        -------
        dict
            Parsed contents of the JSON file the script wrote.

        Raises
        ------
        HistoricalFetchError
            If the subprocess exits non-zero (any of: argparse failure,
            yfinance error, missing price, sanitization issue). The
            stderr text is preserved in the exception message.
        """
        cmd: list[str] = [
            sys.executable,
            str(self.script_path),
            "--ticker", ticker,
            "--market", market,
            "--output", str(output_path),
            "--bundle", bundle,
            "--as-of", as_of.isoformat(),
        ]

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        if completed.returncode != 0:
            raise HistoricalFetchError(
                f"yfinance-collector.py exited with code "
                f"{completed.returncode} for ticker={ticker} "
                f"as_of={as_of.isoformat()}: {completed.stderr.strip()}"
            )

        return json.loads(output_path.read_text(encoding="utf-8"))


__all__ = ["HistoricalFetchError", "YFinanceHistorical"]
