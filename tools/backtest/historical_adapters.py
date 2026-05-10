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
  ``--as-of`` enabled (Task 2.1).
- :class:`FredHistorical` — wraps fred-collector.py with ``--as-of``
  enabled, forwarding to FRED's native ``observation_end`` param
  (Task 2.2).
- :class:`DartHistorical` — wraps dart-collector.py with ``--as-of``
  enabled, capping disclosures via DART's native ``end_de`` and
  filtering periodic-report attempts by statutory filing deadline
  (Task 2.4).

Future tasks (Chunk 2 follow-ups, NOT this file):

- ``SECHistorical`` (Task 2.3) for SEC filings as-of (lives in
  ``sec_historical.py`` rather than here because SEC is via MCP, not a
  subprocess script)

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
_DEFAULT_FRED_SCRIPT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "web-researcher"
    / "scripts"
    / "fred-collector.py"
)
_DEFAULT_DART_SCRIPT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "web-researcher"
    / "scripts"
    / "dart-collector.py"
)
_DEFAULT_TIMEOUT_SECONDS = 60
_DEFAULT_BUNDLE = "standard"
# Sentinel ticker recorded on HistoricalFetchError when the failing
# fetch is series-based (FRED) rather than ticker-based. Keeps the
# exception attribute uniform across adapters.
_FRED_SENTINEL_TICKER = "<fred>"


class HistoricalFetchError(RuntimeError):
    """Raised when an as-of historical fetch fails.

    Carries the subprocess returncode, full stderr, and the (ticker,
    as_of) coordinates so callers can programmatically distinguish
    failure modes (e.g. exit 2 + "future" in stderr vs exit 1 + missing
    price) without regex-matching the message.
    """

    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        stderr: str,
        ticker: str,
        as_of: _dt.date,
    ) -> None:
        super().__init__(message)
        self.returncode: int = returncode
        self.stderr: str = stderr
        self.ticker: str = ticker
        self.as_of: _dt.date = as_of


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
        resolved_output = pathlib.Path(output_path).expanduser().resolve()

        cmd: list[str] = [
            sys.executable,
            str(self.script_path),
            "--ticker", ticker,
            "--market", market,
            "--output", str(resolved_output),
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
                f"as_of={as_of.isoformat()}: {completed.stderr.strip()}",
                returncode=completed.returncode,
                stderr=completed.stderr,
                ticker=ticker,
                as_of=as_of,
            )

        return json.loads(resolved_output.read_text(encoding="utf-8"))


class FredHistorical:
    """Subprocess-driven adapter for fred-collector.py with --as-of.

    FRED is series-based (DGS10, CPIAUCSL, …) rather than ticker-based,
    so the ``fetch`` signature is intentionally different from
    :class:`YFinanceHistorical` — there is no ``ticker`` argument. The
    ``include_kr`` flag toggles the Korean overlay (USD/KRW etc.) by
    passing ``--market KR`` to the underlying script.

    The exception contract still uses :class:`HistoricalFetchError` so
    callers that uniformly read ``exc.ticker`` keep working — for FRED
    the attribute is set to the sentinel ``"<fred>"``.

    Parameters
    ----------
    script_path:
        Optional override for the path to ``fred-collector.py``.
        Defaults to the repo's bundled script. Useful for tests.
    timeout_seconds:
        Wall-clock timeout for the subprocess.
    api_key:
        Optional explicit FRED API key. When ``None`` (default), the
        underlying script reads ``FRED_API_KEY`` from the environment
        (or ``<repo>/.env``).
    """

    def __init__(
        self,
        *,
        script_path: pathlib.Path | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        api_key: str | None = None,
    ) -> None:
        self.script_path: pathlib.Path = (
            script_path if script_path is not None else _DEFAULT_FRED_SCRIPT_PATH
        )
        self.timeout_seconds: int = timeout_seconds
        self.api_key: str | None = api_key

    def fetch(
        self,
        *,
        as_of: _dt.date,
        output_path: pathlib.Path,
        include_kr: bool = False,
    ) -> dict[str, Any]:
        """Fetch the FRED macro snapshot as of ``as_of``.

        The subprocess is invoked with ``--as-of`` so the script
        forwards FRED's native ``observation_end`` to every series
        request. The 24h cache in fred-collector.py is bypassed in
        as-of mode (current-state cache would otherwise leak future
        data into the backtest).

        Parameters
        ----------
        as_of:
            Historical anchor (no future leakage). The collector script
            rejects future dates with exit code 2.
        output_path:
            Where the script should write its JSON output. Parent dirs
            are created by the script.
        include_kr:
            When ``True``, pass ``--market KR`` so the Korean overlay
            (USD/KRW etc.) is included in the snapshot.

        Returns
        -------
        dict
            Parsed contents of the JSON file the script wrote.

        Raises
        ------
        HistoricalFetchError
            If the subprocess exits non-zero. The stderr text is
            preserved on the exception alongside ``returncode`` and
            ``as_of``. The ``ticker`` attribute is set to the sentinel
            ``"<fred>"`` because FRED fetches are series-based.
        """
        resolved_output = pathlib.Path(output_path).expanduser().resolve()

        cmd: list[str] = [
            sys.executable,
            str(self.script_path),
            "--output", str(resolved_output),
            "--as-of", as_of.isoformat(),
        ]
        if include_kr:
            cmd.extend(["--market", "KR"])
        if self.api_key:
            cmd.extend(["--api-key", self.api_key])

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        if completed.returncode != 0:
            raise HistoricalFetchError(
                f"fred-collector.py exited with code "
                f"{completed.returncode} for as_of={as_of.isoformat()}: "
                f"{completed.stderr.strip()}",
                returncode=completed.returncode,
                stderr=completed.stderr,
                ticker=_FRED_SENTINEL_TICKER,
                as_of=as_of,
            )

        return json.loads(resolved_output.read_text(encoding="utf-8"))


class DartHistorical:
    """Subprocess-driven adapter for dart-collector.py with --as-of.

    DART (금융감독원 전자공시) is the Korean regulatory disclosure system,
    keyed by 6-digit KRX stock code rather than US-style ticker symbol.
    The ``fetch`` signature uses ``ticker`` for surface uniformity with
    :class:`YFinanceHistorical`; for KR equities the value is the
    6-digit code (e.g. ``"005930"`` for Samsung Electronics).

    Backtest semantics handled by the underlying script:

    - ``end_de`` is set to ``--as-of`` so the disclosures list never
      surfaces filings dated after the historical anchor.
    - The periodic-report ``attempts`` list is filtered to only include
      reports whose **statutory filing deadline** is on or before
      ``--as-of``. We err on the side of skipping a period rather than
      including a not-yet-filed report and leaking future data.

    Parameters
    ----------
    script_path:
        Optional override for the path to ``dart-collector.py``.
        Defaults to the repo's bundled script. Useful for tests.
    timeout_seconds:
        Wall-clock timeout for the subprocess. DART's corpCode.xml
        lookup can be slow on first call (multi-MB ZIP download) so the
        default leaves room for that.
    api_key:
        Optional explicit DART API key. When ``None`` (default), the
        underlying script reads ``DART_API_KEY`` from the environment
        (or ``<repo>/.env``).
    """

    def __init__(
        self,
        *,
        script_path: pathlib.Path | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        api_key: str | None = None,
    ) -> None:
        self.script_path: pathlib.Path = (
            script_path if script_path is not None else _DEFAULT_DART_SCRIPT_PATH
        )
        self.timeout_seconds: int = timeout_seconds
        self.api_key: str | None = api_key

    def fetch(
        self,
        *,
        ticker: str,
        as_of: _dt.date,
        output_path: pathlib.Path,
    ) -> dict[str, Any]:
        """Fetch DART data as of ``as_of`` and return the parsed JSON.

        Parameters
        ----------
        ticker:
            6-digit KRX stock code (e.g. ``"005930"``). Forwarded to
            ``--stock-code`` on the underlying script.
        as_of:
            Historical anchor (no future leakage). The collector script
            rejects future dates with exit code 2.
        output_path:
            Where the script should write its JSON output. Parent dirs
            are created by the script.

        Returns
        -------
        dict
            Parsed contents of the JSON file the script wrote.

        Raises
        ------
        HistoricalFetchError
            If the subprocess exits non-zero. The stderr text is
            preserved on the exception alongside ``returncode``,
            ``ticker``, and ``as_of``.
        """
        resolved_output = pathlib.Path(output_path).expanduser().resolve()

        cmd: list[str] = [
            sys.executable,
            str(self.script_path),
            "--stock-code", ticker,
            "--output", str(resolved_output),
            "--as-of", as_of.isoformat(),
        ]
        if self.api_key:
            cmd.extend(["--api-key", self.api_key])

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        if completed.returncode != 0:
            raise HistoricalFetchError(
                f"dart-collector.py exited with code "
                f"{completed.returncode} for ticker={ticker} "
                f"as_of={as_of.isoformat()}: {completed.stderr.strip()}",
                returncode=completed.returncode,
                stderr=completed.stderr,
                ticker=ticker,
                as_of=as_of,
            )

        return json.loads(resolved_output.read_text(encoding="utf-8"))


__all__ = [
    "DartHistorical",
    "FredHistorical",
    "HistoricalFetchError",
    "YFinanceHistorical",
]
