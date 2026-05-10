"""Backtest harness package.

Holds the as-of-date-aware scaffolding that lets the Stock Analysis
Agent pipeline run against historical dates so we can measure forward
predictive power. See ``docs/superpowers/plans/2026-05-08-backtest-
harness.md`` for the multi-chunk plan.

Public API:

- :class:`BacktestContext` — frozen scope object (cohort, ticker,
  as-of date) plus run-id and artifact-root helpers.
"""

from __future__ import annotations

from tools.backtest.pipeline_context import BacktestContext

__all__ = ["BacktestContext"]
