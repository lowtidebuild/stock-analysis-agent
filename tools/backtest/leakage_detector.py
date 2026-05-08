"""Leakage detector for backtest pipeline as-of date enforcement.

A backtest run pretends "today" is some historical date (``as_of``). If any
fetched artifact contains data dated *after* that date, the run is leaking
look-ahead information and its results cannot be trusted. This module walks
fetched JSON payloads and surfaces any date-shaped field whose value lies
beyond the requested ``as_of``.

The detector is **separate from**
:mod:`tools.prompt_injection_filter`. The injection filter sanitizes
*untrusted text content* (news bodies, snippets, filing text) so the
analyst cannot be redirected by adversarial input. This module enforces
*temporal correctness*: even fully-trusted aggregator data must respect
the historical cutoff. Both layers run on the same artifacts but check
orthogonal properties.

Behavior summary
----------------
- Recursively walks dicts and lists (other types are ignored).
- Inspects only string-valued fields whose key name (case-insensitive)
  ends in ``_date`` or ``_datetime``. Free-text fields like ``name`` /
  ``description`` are skipped even if they contain date-shaped
  substrings.
- Parses values with :meth:`datetime.date.fromisoformat` first; if that
  fails, falls back to :meth:`datetime.datetime.fromisoformat`. Values
  that fail both parsers are still recorded as findings — fetchers
  shouldn't be emitting garbage in date positions.
- Strict mode (the default) raises :class:`LeakageError` on the first
  finding so the cohort runner can fail loud. Lenient mode collects every
  finding and returns the list.

This module is invoked by the cohort runner / orchestrator (Chunk 3 of
the backtest harness plan) — it is intentionally decoupled from
:class:`tools.backtest.pipeline_context.BacktestContext` so the same
checker can be unit-tested against synthetic payloads.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any

_DATE_SUFFIXES = ("_date", "_datetime")

_KIND_FUTURE_DATE = "future_date"
_KIND_FUTURE_DATETIME = "future_datetime"
_KIND_UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class LeakageFinding:
    """A single look-ahead leakage finding.

    Parameters
    ----------
    path:
        JSON-pointer-like path to the offending field, rooted at the
        ``source_label`` passed to :meth:`LeakageDetector.check`. List
        indices use ``[i]`` notation. Example::

            tier2-raw.json.news_items[3].published_date

    field_name:
        The dict key whose suffix triggered the inspection (e.g.
        ``"published_date"``).
    value:
        The raw offending value, stringified for diagnostics.
    kind:
        One of:

        - ``"future_date"`` — parsed as :class:`datetime.date` and
          strictly greater than ``as_of``.
        - ``"future_datetime"`` — parsed as :class:`datetime.datetime`
          and its ``.date()`` is strictly greater than ``as_of``.
        - ``"unparseable"`` — neither parser succeeded, or the value
          was not even a string.
    """

    path: str
    field_name: str
    value: str
    kind: str


class LeakageError(RuntimeError):
    """Raised by :meth:`LeakageDetector.check` in strict mode.

    The exception carries the offending finding(s) on
    :attr:`findings` so callers can render a useful error message
    without re-walking the payload.
    """

    def __init__(self, findings: list[LeakageFinding]) -> None:
        self.findings = list(findings)
        if findings:
            first = findings[0]
            msg = (
                f"Leakage detected at {first.path} "
                f"(kind={first.kind}, value={first.value!r})"
            )
        else:  # pragma: no cover — defensive; callers always pass ≥1 finding.
            msg = "Leakage detected (no findings attached)"
        super().__init__(msg)


class LeakageDetector:
    """Walk a payload and flag any date field that exceeds ``as_of``.

    Parameters
    ----------
    strict:
        When ``True`` (the default) the first finding raises
        :class:`LeakageError`. When ``False`` every finding is collected
        and returned without raising. Lenient mode is useful for the
        eval harness, which wants a full inventory of leaks before the
        run is rejected.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self._strict = strict

    def check(
        self,
        payload: object,
        as_of: _dt.date,
        *,
        source_label: str = "<root>",
    ) -> list[LeakageFinding]:
        """Walk ``payload`` and return a list of :class:`LeakageFinding`.

        Parameters
        ----------
        payload:
            The fetched object to inspect. Typically a ``dict`` parsed
            from a tier1 / tier2 / dart-api raw JSON file. Non-container
            payloads are accepted (and yield no findings) so the walker
            never crashes on unexpected input.
        as_of:
            The backtest as-of date. A field value is flagged when it
            parses to a date strictly greater than ``as_of``.
        source_label:
            The string used as the root segment of each finding's
            ``path``. Callers typically pass the artifact filename (e.g.
            ``"tier2-raw.json"``) so findings are self-describing.

        Returns
        -------
        list[LeakageFinding]
            Empty when nothing was flagged. In strict mode the method
            raises before returning if any finding is produced.

        Raises
        ------
        LeakageError
            In strict mode, raised on the first finding. The exception
            carries the single finding on its ``.findings`` attribute.
        """
        findings: list[LeakageFinding] = []
        self._walk(payload, as_of, path=source_label, findings=findings)
        return findings

    # ------------------------------------------------------------------
    # Internal recursion
    # ------------------------------------------------------------------

    def _walk(
        self,
        node: Any,
        as_of: _dt.date,
        *,
        path: str,
        findings: list[LeakageFinding],
    ) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if isinstance(key, str) and self._is_date_key(key):
                    self._inspect_date_value(
                        value,
                        as_of,
                        path=child_path,
                        field_name=key,
                        findings=findings,
                    )
                # Always recurse — nested containers may carry their
                # own *_date fields even under a non-date key.
                self._walk(value, as_of, path=child_path, findings=findings)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                child_path = f"{path}[{index}]"
                self._walk(item, as_of, path=child_path, findings=findings)
        # Scalars at non-date keys are ignored — _inspect_date_value
        # already handled the date-key case above.

    def _inspect_date_value(
        self,
        value: Any,
        as_of: _dt.date,
        *,
        path: str,
        field_name: str,
        findings: list[LeakageFinding],
    ) -> None:
        # Skip None silently — fetchers commonly emit null when a field
        # is unknown, and that's not a leak.
        if value is None:
            return

        if not isinstance(value, str):
            self._record(
                findings,
                LeakageFinding(
                    path=path,
                    field_name=field_name,
                    value=str(value),
                    kind=_KIND_UNPARSEABLE,
                ),
            )
            return

        kind = self._classify(value, as_of)
        if kind is None:
            return
        self._record(
            findings,
            LeakageFinding(
                path=path,
                field_name=field_name,
                value=value,
                kind=kind,
            ),
        )

    def _record(
        self,
        findings: list[LeakageFinding],
        finding: LeakageFinding,
    ) -> None:
        findings.append(finding)
        if self._strict:
            raise LeakageError(findings)

    @staticmethod
    def _is_date_key(key: str) -> bool:
        lowered = key.lower()
        return any(lowered.endswith(suffix) for suffix in _DATE_SUFFIXES)

    @staticmethod
    def _classify(value: str, as_of: _dt.date) -> str | None:
        """Return the finding kind for ``value``, or ``None`` if clean."""
        # Try plain date first (covers "2025-04-15").
        try:
            parsed_date = _dt.date.fromisoformat(value)
        except ValueError:
            parsed_date = None

        if parsed_date is not None:
            return _KIND_FUTURE_DATE if parsed_date > as_of else None

        # Fall back to datetime (covers "2025-04-15T12:00:00",
        # "2025-04-15T12:00:00+09:00", and Python 3.11+ "Z" suffix).
        try:
            parsed_dt = _dt.datetime.fromisoformat(value)
        except ValueError:
            return _KIND_UNPARSEABLE

        return _KIND_FUTURE_DATETIME if parsed_dt.date() > as_of else None


__all__ = ["LeakageDetector", "LeakageError", "LeakageFinding"]
