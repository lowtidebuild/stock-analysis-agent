#!/usr/bin/env python3
"""Legacy Mode A headless runner with a native all-mode bridge.

Without ``--native``, this script keeps the original Mode A web-runner contract
available for compatibility. New Codex-native Mode A/B/C delivery should use
``scripts/run_mode.py`` directly, or pass ``--native`` here to delegate to it.

Asset survey for future maintainers:
- data collection: .claude/skills/financial-data-collector/scripts/yfinance-collector.py
- validation helpers: .claude/skills/data-validator/scripts/validate-artifacts.py
- Mode A renderer: .claude/skills/briefing-generator/scripts/render-briefing.py
- Mode C final renderer warning: docs/adr/0001-mode-c-rendering-strategy.ko.md
- analyst prompt source: .claude/agents/analyst/AGENT.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyst_backends import get_backend  # noqa: E402


class PipelineError(RuntimeError):
    pass


LEGACY_WEB_RUNNER_WARNING = (
    "WARNING: scripts/run_analysis.py without --native is deprecated and remains "
    "only for legacy Mode A web-runner compatibility. Use scripts/run_mode.py or "
    "scripts/run_analysis.py --native for Codex-native delivery."
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ticker = args.ticker.strip().upper()
    mode = args.mode.strip().upper()
    language = args.lang.strip().lower()
    market = normalize_market(args.market, ticker)
    run_id = args.run_id.strip()

    if args.native:
        return run_native_mode(args)

    if mode == "C":
        raise PipelineError(
            "Mode C headless renderer is not production-ready yet. "
            "Use scripts/run_mode.py, scripts/run_mode_c.py, or pass --native."
        )
    if mode != "A":
        raise PipelineError("Local Runner MVP currently supports Mode A only. Pass --native for all-mode native delivery.")

    emit_legacy_web_runner_warning()
    paths = build_paths(run_id, ticker)
    for path in [paths["ticker_root"], paths["reports_dir"]]:
        path.mkdir(parents=True, exist_ok=True)

    analysis_date = datetime.now(UTC).strftime("%Y-%m-%d")
    write_json(paths["research_plan"], build_research_plan(ticker, mode, language, market))
    raw = collect_market_data(ticker, market, paths["yfinance_raw"])
    validated = build_validated_data(raw, ticker, market, analysis_date, language)
    write_json(paths["validated_data"], validated)
    evidence_pack = build_evidence_pack(validated, raw)
    write_json(paths["evidence_pack"], evidence_pack)
    write_json(paths["context_budget"], build_context_budget(validated))

    analyst_json, backend_meta = run_analyst(
        evidence_pack=evidence_pack,
        language=language,
        mode=mode,
        ticker=ticker,
        validated=validated,
    )
    analysis = enrich_analysis_result(
        analyst_json,
        backend_meta=backend_meta,
        language=language,
        mode=mode,
        paths=paths,
        ticker=ticker,
        validated=validated,
    )
    validate_analysis_result(analysis)
    write_json(paths["analysis_result"], analysis)

    report_path = paths["reports_dir"] / f"{ticker}_{mode}_{language}_{analysis_date}.html"
    render_mode_a(paths["analysis_result"], report_path)
    run_quality_gate(report_path, min_bytes=8_000)
    write_json(paths["quality_report"], build_quality_report(analysis, report_path))
    print(json.dumps({"report_path": str(report_path), "run_id": run_id}, ensure_ascii=False))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one stock analysis through the legacy Mode A runner or the native all-mode CLI.",
        epilog=(
            "Without --native this script only runs the deprecated legacy Mode A "
            "web-runner. Prefer scripts/run_mode.py for new Codex-native delivery."
        ),
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--mode", required=True, choices=["A", "B", "C", "a", "b", "c"])
    parser.add_argument("--lang", required=True, choices=["ko", "en"])
    parser.add_argument("--market", required=True, choices=["US", "KR", "mixed", "auto"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--native",
        action="store_true",
        help="Delegate to scripts/run_mode.py for Codex-native Mode A/B/C delivery.",
    )
    parser.add_argument("--skip-network", action="store_true")
    parser.add_argument("--reuse-collected", action="store_true")
    parser.add_argument("--peer-tickers", default="")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--run-profile",
        choices=["production", "smoke", "fixture"],
        default=None,
        help="Native delivery profile. Defaults to smoke for fixture backends and production otherwise.",
    )
    parser.add_argument(
        "--allow-fixture-delivery",
        action="store_true",
        help="Allow fixture/smoke native runs to pass delivery for deterministic tests.",
    )
    parser.add_argument(
        "--allow-deterministic-delivery",
        action="store_true",
        help="Allow deterministic template native runs to pass delivery with a visible disclosure flag.",
    )
    parser.add_argument(
        "--web-provider",
        choices=["tavily", "brave", "none"],
        default=None,
        help="Override WEB_SEARCH_PROVIDER for native Mode C tier2 qualitative search.",
    )
    parser.add_argument(
        "--analyst-backend",
        default=None,
        help="Override native ANALYST_BACKEND, for example codex_native or fixture.",
    )
    return parser.parse_args(argv)


def emit_legacy_web_runner_warning() -> None:
    print(LEGACY_WEB_RUNNER_WARNING, file=sys.stderr)


def run_native_mode(args: argparse.Namespace) -> int:
    from scripts.run_mode import main as run_mode_main

    forwarded = [
        "--ticker",
        args.ticker,
        "--mode",
        args.mode,
        "--lang",
        args.lang,
        "--market",
        args.market,
        "--run-id",
        args.run_id,
    ]
    if args.tickers:
        forwarded.extend(["--tickers", args.tickers])
    if args.skip_network:
        forwarded.append("--skip-network")
    if args.reuse_collected:
        forwarded.append("--reuse-collected")
    if args.peer_tickers:
        forwarded.extend(["--peer-tickers", args.peer_tickers])
    if args.timeout is not None:
        forwarded.extend(["--timeout", str(args.timeout)])
    if args.run_profile:
        forwarded.extend(["--run-profile", args.run_profile])
    if args.allow_fixture_delivery:
        forwarded.append("--allow-fixture-delivery")
    if args.allow_deterministic_delivery:
        forwarded.append("--allow-deterministic-delivery")
    if args.web_provider:
        forwarded.extend(["--web-provider", args.web_provider])
    if args.analyst_backend:
        forwarded.extend(["--analyst-backend", args.analyst_backend])
    return run_mode_main(forwarded)


def normalize_market(value: str, ticker: str) -> str:
    if value == "auto":
        return "KR" if ticker.isdigit() and len(ticker) == 6 else "US"
    return value


def build_paths(run_id: str, ticker: str) -> dict[str, Path]:
    ticker_root = REPO_ROOT / "output" / "runs" / run_id / ticker
    return {
        "ticker_root": ticker_root,
        "reports_dir": REPO_ROOT / "output" / "reports",
        "research_plan": ticker_root / "research-plan.json",
        "yfinance_raw": ticker_root / "yfinance-raw.json",
        "validated_data": ticker_root / "validated-data.json",
        "evidence_pack": ticker_root / "evidence-pack.json",
        "context_budget": ticker_root / "context-budget.json",
        "analysis_result": ticker_root / "analysis-result.json",
        "quality_report": ticker_root / "quality-report.json",
    }


def collect_market_data(ticker: str, market: str, output_path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        ".claude/skills/financial-data-collector/scripts/yfinance-collector.py",
        "--ticker",
        ticker,
        "--market",
        market,
        "--output",
        str(output_path.relative_to(REPO_ROOT)),
        "--bundle",
        "standard",
        "--timeout",
        "20",
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        message = result.stderr.strip() or result.stdout.strip() or "data collection failed"
        raise PipelineError(message[-2000:])
    if not output_path.exists():
        raise PipelineError("data collection did not write yfinance-raw.json")
    return load_json(output_path)


def build_research_plan(ticker: str, mode: str, language: str, market: str) -> dict[str, Any]:
    return {
        "schema_version": "web-runner-research-plan-v1",
        "ticker": ticker,
        "market": market,
        "output_mode": mode,
        "output_language": language,
        "data_mode": "standard",
        "analysis_framework_path": "references/analysis-framework-briefing.md",
        "created_at": utc_now(),
    }


def build_validated_data(
    raw: dict[str, Any],
    ticker: str,
    market: str,
    analysis_date: str,
    language: str,
) -> dict[str, Any]:
    price = raw.get("current_price") if isinstance(raw.get("current_price"), dict) else {}
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    derived = raw.get("derived_ttm") if isinstance(raw.get("derived_ttm"), dict) else {}
    analyst_targets = (
        raw.get("analyst_targets") if isinstance(raw.get("analyst_targets"), dict) else {}
    )
    income_rows = (
        raw.get("income_statements")
        if isinstance(raw.get("income_statements"), list)
        else []
    )
    cashflow_rows = (
        raw.get("cash_flow_statements")
        if isinstance(raw.get("cash_flow_statements"), list)
        else []
    )
    balance_rows = (
        raw.get("balance_sheets") if isinstance(raw.get("balance_sheets"), list) else []
    )
    if price.get("price") is None:
        raise PipelineError("current_price.price is required for Mode A analysis")

    company_name = (
        raw.get("company_name")
        or info.get("long_name")
        or info.get("short_name")
        or raw.get("company_name")
        or ticker
    )
    currency = price.get("currency") or info.get("currency") or "USD"
    market_cap = info.get("market_cap")
    revenue_ttm = derived.get("revenue_ttm") or info.get("total_revenue")
    operating_income_ttm = derived.get("operating_income_ttm")
    net_income_ttm = derived.get("net_income_ttm") or info.get("net_income_to_common")
    fcf_ttm = derived.get("fcf_ttm") or info.get("free_cashflow")
    operating_cashflow_ttm = sum_recent(cashflow_rows, "operating_cashflow", 4)
    capex_ttm = sum_recent(cashflow_rows, "capital_expenditure", 4)
    latest_quarter = first_dict(income_rows)
    latest_balance = first_dict(balance_rows)
    revenue_growth_yoy = quarter_yoy_growth(income_rows, "revenue")
    operating_margin = safe_pct(operating_income_ttm, revenue_ttm)
    net_margin = safe_pct(net_income_ttm, revenue_ttm)
    fcf_yield = safe_pct(fcf_ttm, market_cap)
    total_debt = latest_balance.get("total_debt")
    cash = latest_balance.get("cash_and_equivalents")
    net_debt = safe_subtract(total_debt, cash)
    implied_ebitda = safe_div(info.get("enterprise_value"), info.get("ev_ebitda"))
    net_debt_ebitda = safe_div(net_debt, implied_ebitda)

    metrics = {
        "price": metric(price.get("price"), currency=currency, source="yfinance current price"),
        "market_cap": metric(
            billions(market_cap),
            unit="billions",
            currency=currency,
            source="yfinance marketCap",
        ),
        "pe_forward": metric(info.get("pe_forward"), unit="x", source="yfinance forwardPE"),
        "pe_trailing": metric(info.get("pe_trailing"), unit="x", source="yfinance trailingPE"),
        "ev_ebitda": metric(info.get("ev_ebitda"), unit="x", source="yfinance enterpriseToEbitda"),
        "pb_ratio": metric(info.get("pb_ratio"), unit="x", source="yfinance priceToBook"),
        "revenue_ttm": metric(
            billions(revenue_ttm),
            unit="billions",
            currency=currency,
            source="yfinance trailing four quarters",
        ),
        "revenue_growth_yoy": metric(
            revenue_growth_yoy,
            unit="percent",
            source="yfinance latest quarter vs year-ago quarter",
        ),
        "operating_margin": metric(
            operating_margin,
            unit="percent",
            source="calculated operating income / revenue",
        ),
        "net_margin": metric(
            net_margin,
            unit="percent",
            source="calculated net income / revenue",
        ),
        "fcf_ttm": metric(
            billions(fcf_ttm),
            unit="billions",
            currency=currency,
            source="yfinance trailing four quarters",
        ),
        "fcf_yield": metric(fcf_yield, unit="percent", source="calculated FCF / market cap"),
        "operating_cashflow_ttm": metric(
            billions(operating_cashflow_ttm),
            unit="billions",
            currency=currency,
            source="yfinance trailing four quarters",
        ),
        "capex_ttm": metric(
            billions(capex_ttm),
            unit="billions",
            currency=currency,
            source="yfinance trailing four quarters",
        ),
        "net_debt_ebitda": metric(
            net_debt_ebitda,
            unit="x",
            source="calculated net debt / implied EBITDA",
        ),
        "analyst_target_mean": metric(
            analyst_targets.get("mean_target"),
            currency=currency,
            source="yfinance analyst target mean",
            tag="[Est]",
        ),
        "analyst_target_median": metric(
            analyst_targets.get("median_target"),
            currency=currency,
            source="yfinance analyst target median",
            tag="[Est]",
        ),
        "analyst_target_high": metric(
            analyst_targets.get("high_target"),
            currency=currency,
            source="yfinance analyst target high",
            tag="[Est]",
        ),
        "analyst_target_low": metric(
            analyst_targets.get("low_target"),
            currency=currency,
            source="yfinance analyst target low",
            tag="[Est]",
        ),
        "beta": metric(info.get("beta"), source="yfinance beta"),
        "fifty_two_week_high": metric(info.get("fifty_two_week_high"), currency=currency, source="yfinance 52W high"),
        "fifty_two_week_low": metric(info.get("fifty_two_week_low"), currency=currency, source="yfinance 52W low"),
    }
    timeline_events = build_timeline_events(
        income_rows=income_rows,
        language=language,
        raw=raw,
        latest_quarter=latest_quarter,
        price=price,
        revenue_growth_yoy=revenue_growth_yoy,
        ticker=ticker,
    )
    scenario_anchors = build_scenario_anchors(
        analyst_targets=analyst_targets,
        currency=currency,
        language=language,
        metrics=metrics,
        price=price.get("price"),
    )
    return {
        "schema_version": "web-runner-validated-data-v1",
        "ticker": ticker,
        "company_name": company_name,
        "market": market,
        "company_type": classify_company_type(info, market),
        "data_mode": "standard",
        "source_profile": "yfinance_structured_runner",
        "source_tier": "portal_plus_calc",
        "confidence_cap": "B",
        "validation_timestamp": utc_now(),
        "analysis_date": analysis_date,
        "overall_grade": "B",
        "currency": currency,
        "price_day_change": price.get("change"),
        "price_day_change_pct": price.get("change_pct"),
        "validated_metrics": metrics,
        "scenario_anchors": scenario_anchors,
        "timeline_events": timeline_events,
        "latest_quarter": latest_quarter,
        "exclusions": [],
        "metric_conflicts": [],
        "sanity_alerts": build_sanity_alerts(metrics),
        "_validation": {"runner": "scripts/run_analysis.py"},
        "_sanitization": raw.get("_sanitization") or {"status": "collector_output"},
    }


def metric(
    value: Any,
    *,
    currency: str | None = None,
    source: str,
    tag: str = "[Portal]",
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "grade": "B" if value is not None else "D",
        "source_type": "estimate" if tag == "[Est]" else "portal_global",
        "source_authority": "market_portal",
        "display_tag": tag,
        "tag": tag,
        "currency": currency,
        "sources": [source],
    }


def first_dict(rows: list[Any]) -> dict[str, Any]:
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def safe_div(numerator: Any, denominator: Any) -> float | None:
    left = as_number(numerator)
    right = as_number(denominator)
    if left is None or right in (None, 0):
        return None
    return left / right


def safe_pct(numerator: Any, denominator: Any) -> float | None:
    value = safe_div(numerator, denominator)
    return round(value * 100, 2) if value is not None else None


def safe_subtract(left: Any, right: Any) -> float | None:
    left_number = as_number(left)
    right_number = as_number(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def billions(value: Any) -> float | None:
    number = as_number(value)
    return round(number / 1_000_000_000, 2) if number is not None else None


def sum_recent(rows: list[Any], field: str, limit: int) -> float | None:
    values = [
        as_number(row.get(field))
        for row in rows[:limit]
        if isinstance(row, dict) and as_number(row.get(field)) is not None
    ]
    return sum(values) if values else None


def quarter_yoy_growth(rows: list[Any], field: str) -> float | None:
    latest = first_dict(rows)
    latest_value = as_number(latest.get(field))
    latest_period = str(latest.get("period_end") or "")
    if latest_value is None or len(latest_period) < 10:
        return None
    latest_suffix = latest_period[4:10]
    try:
        prior_year = int(latest_period[:4]) - 1
    except ValueError:
        return None
    target_period = f"{prior_year}{latest_suffix}"
    for row in rows[1:]:
        if not isinstance(row, dict):
            continue
        if str(row.get("period_end") or "")[:10] == target_period:
            prior_value = as_number(row.get(field))
            if prior_value not in (None, 0):
                return round(((latest_value - prior_value) / prior_value) * 100, 2)
    return None


def classify_company_type(info: dict[str, Any], market: str) -> str:
    if market == "KR":
        return "Korean equity"
    sector = str(info.get("sector") or "")
    industry = str(info.get("industry") or "")
    descriptor = f"{sector} / {industry}".strip(" /")
    if "Internet" in industry or "Software" in industry or "Technology" in sector:
        return f"Technology - {descriptor}" if descriptor else "Technology"
    return descriptor or "US equity"


def build_sanity_alerts(metrics: dict[str, dict[str, Any]]) -> list[str]:
    alerts = []
    fcf_yield = as_number(metrics.get("fcf_yield", {}).get("value"))
    pe_forward = as_number(metrics.get("pe_forward", {}).get("value"))
    revenue_growth = as_number(metrics.get("revenue_growth_yoy", {}).get("value"))
    if fcf_yield is not None and fcf_yield < 2:
        alerts.append("FCF yield below 2%; valuation depends on future FCF recovery.")
    if pe_forward is not None and pe_forward > 25 and (revenue_growth is None or revenue_growth < 15):
        alerts.append("Forward P/E above 25x without verified 15%+ latest-quarter revenue growth.")
    return alerts


def build_scenario_anchors(
    *,
    analyst_targets: dict[str, Any],
    currency: str,
    language: str,
    metrics: dict[str, dict[str, Any]],
    price: Any,
) -> dict[str, Any]:
    current = as_number(price)
    mean_target = as_number(analyst_targets.get("mean_target"))
    median_target = as_number(analyst_targets.get("median_target"))
    high_target = as_number(analyst_targets.get("high_target"))
    low_target = as_number(analyst_targets.get("low_target"))
    high_52w = as_number(metrics.get("fifty_two_week_high", {}).get("value"))
    low_52w = as_number(metrics.get("fifty_two_week_low", {}).get("value"))
    if current is None:
        return {}

    base_target = median_target or mean_target or current
    bull_target = high_target or max(base_target * 1.12, high_52w or base_target)
    if low_target is not None and low_target < current:
        bear_target = max(min(low_target, current * 0.72), current * 0.5)
    elif low_52w is not None and low_52w < current:
        bear_target = max(min(low_52w, current * 0.72), current * 0.5)
    else:
        bear_target = current * 0.78
    probabilities = {"bull": 0.25, "base": 0.45, "bear": 0.30}
    if language == "ko":
        assumptions = {
            "bull": "고성장과 FCF 전환 개선이 동시에 확인되어 컨센서스 상단 목표가가 유지되는 경우.",
            "base": "컨센서스 중앙/평균 목표가가 실현되고 주요 추정치 하향이 없는 경우.",
            "bear": "얕은 web-runner 근거를 감안한 보수적 디레이팅 케이스; 하단 컨센서스 또는 28% 하락 중 더 낮은 값을 적용.",
        }
    else:
        assumptions = {
            "bull": "High growth and improving FCF conversion keep the consensus high-case target intact.",
            "base": "Consensus median/mean target is realized with no major estimate reset.",
            "bear": "Conservative derating case for thin web-runner evidence; uses the lower of downside consensus or a 28% drawdown.",
        }

    scenarios = {
        "bull": {
            "target": round(bull_target, 2),
            "return_pct": round((bull_target / current - 1) * 100, 2),
            "probability": probabilities["bull"],
            "key_assumption": assumptions["bull"],
        },
        "base": {
            "target": round(base_target, 2),
            "return_pct": round((base_target / current - 1) * 100, 2),
            "probability": probabilities["base"],
            "key_assumption": assumptions["base"],
        },
        "bear": {
            "target": round(bear_target, 2),
            "return_pct": round((bear_target / current - 1) * 100, 2),
            "probability": probabilities["bear"],
            "key_assumption": assumptions["bear"],
        },
    }
    rr_score = calculate_rr_score(scenarios)
    return {
        "currency": currency,
        "current_price": current,
        "method": "analyst target anchored quick scenario",
        "rr_score": rr_score,
        "scenarios": scenarios,
    }


def calculate_rr_score(scenarios: dict[str, dict[str, Any]]) -> float | None:
    bull = scenarios.get("bull", {})
    base = scenarios.get("base", {})
    bear = scenarios.get("bear", {})
    upside = (
        (as_number(bull.get("return_pct")) or 0) * (as_number(bull.get("probability")) or 0)
        + (as_number(base.get("return_pct")) or 0) * (as_number(base.get("probability")) or 0)
    )
    downside = abs(
        (as_number(bear.get("return_pct")) or 0)
        * (as_number(bear.get("probability")) or 0)
    )
    if downside == 0:
        return None
    return round(upside / downside, 2)


def build_timeline_events(
    *,
    income_rows: list[Any],
    language: str,
    latest_quarter: dict[str, Any],
    price: dict[str, Any],
    raw: dict[str, Any],
    revenue_growth_yoy: float | None,
    ticker: str,
) -> dict[str, list[dict[str, str]]]:
    latest_period = str(latest_quarter.get("period_end") or "")
    revenue = billions(latest_quarter.get("revenue"))
    operating_income = billions(latest_quarter.get("operating_income"))
    net_income = billions(latest_quarter.get("net_income"))
    history = (
        raw.get("historical_prices", {}).get("rows")
        if isinstance(raw.get("historical_prices"), dict)
        else []
    )
    high_event = price_extreme_event(history, "high", max)
    low_event = price_extreme_event(history, "low", min)

    past = []
    if latest_period:
        growth = f", revenue YoY {revenue_growth_yoy:+.1f}%" if revenue_growth_yoy is not None else ""
        event = f"{ticker} 최근 분기 실적" if language == "ko" else f"{ticker} latest quarterly results"
        narrative = (
            f"매출 ${revenue}B{growth}, 영업이익 ${operating_income}B, 순이익 ${net_income}B; 현재 투자 판단의 핵심 펀더멘털 기준점입니다."
            if language == "ko"
            else f"Revenue ${revenue}B{growth}, operating income ${operating_income}B, net income ${net_income}B; this is the main fresh fundamental anchor."
        )
        past.append(
            {
                "date": latest_period,
                "event": event,
                "significance": "high",
                "narrative": narrative,
            }
        )
    if high_event:
        localize_price_event(high_event, language)
        past.append(high_event)
    if low_event and len(past) < 3:
        localize_price_event(low_event, language)
        past.append(low_event)
    if len(past) < 3 and len(income_rows) > 1 and isinstance(income_rows[1], dict):
        prior = income_rows[1]
        past.append(
            {
                "date": str(prior.get("period_end") or "recent quarter"),
                "event": f"{ticker} 직전 분기 비교 기준" if language == "ko" else f"{ticker} prior quarter comparison base",
                "significance": "medium",
                "narrative": (
                    f"직전 분기 매출 ${billions(prior.get('revenue'))}B와 영업이익 ${billions(prior.get('operating_income'))}B는 순차 비교 기준입니다."
                    if language == "ko"
                    else f"Prior-quarter revenue ${billions(prior.get('revenue'))}B and operating income ${billions(prior.get('operating_income'))}B provide the sequential comparison base."
                ),
            }
        )

    next_earnings = estimate_next_earnings_date(latest_period)
    if language == "ko":
        future = [
            {
                "date": next_earnings,
                "event": f"{ticker} 다음 분기 실적 발표 예상 구간",
                "significance": "high",
                "narrative": "매출 성장률, 영업이익률, FCF 전환이 현재 멀티플을 지지하는지 확인해야 합니다.",
            },
            {
                "date": (datetime.now(UTC).date() + timedelta(days=90)).isoformat(),
                "event": f"{ticker} 90일 밸류에이션 점검",
                "significance": "medium",
                "narrative": "다음 보고 사이클 이후 애널리스트 목표가 분포, 선행 P/E, 52주 고가/저가 대비 위치를 재평가합니다.",
            },
        ]
    else:
        future = [
            {
                "date": next_earnings,
                "event": f"{ticker} next quarterly earnings window",
                "significance": "high",
                "narrative": "Watch whether revenue growth, operating margin, and FCF conversion support the current multiple.",
            },
            {
                "date": (datetime.now(UTC).date() + timedelta(days=90)).isoformat(),
                "event": f"{ticker} 90-day valuation checkpoint",
                "significance": "medium",
                "narrative": "Re-score the analyst target spread, forward P/E, and distance to 52-week high/low after the next reporting cycle.",
            },
        ]
    return {"past": past[:4], "future": future}


def price_extreme_event(rows: Any, field: str, chooser: Any) -> dict[str, str] | None:
    if not isinstance(rows, list):
        return None
    candidates = [
        row for row in rows if isinstance(row, dict) and as_number(row.get(field)) is not None
    ]
    if not candidates:
        return None
    selected = chooser(candidates, key=lambda row: as_number(row.get(field)) or 0)
    label = "52-week high test" if field == "high" else "52-week low reference"
    significance = "medium" if field == "high" else "low"
    return {
        "date": str(selected.get("date") or "recent"),
        "event": label,
        "significance": significance,
        "narrative": f"Price {field} ${as_number(selected.get(field)):.2f}; use this level as a sentiment and drawdown reference.",
    }


def localize_price_event(event: dict[str, str], language: str) -> None:
    if language != "ko":
        return
    if event.get("event") == "52-week high test":
        event["event"] = "52주 고가 테스트"
        event["narrative"] = event.get("narrative", "").replace(
            "Price high", "주가 고가"
        ).replace(
            "; use this level as a sentiment and drawdown reference.",
            "; 이 가격은 투자심리와 단기 되돌림 위험의 기준선입니다.",
        )
    elif event.get("event") == "52-week low reference":
        event["event"] = "52주 저가 기준점"
        event["narrative"] = event.get("narrative", "").replace(
            "Price low", "주가 저가"
        ).replace(
            "; use this level as a sentiment and drawdown reference.",
            "; 이 가격은 장기 반등 폭과 하방 스트레스의 기준점입니다.",
        )


def estimate_next_earnings_date(latest_period: str) -> str:
    try:
        quarter_end = datetime.strptime(latest_period[:10], "%Y-%m-%d").date()
    except ValueError:
        return (datetime.now(UTC).date() + timedelta(days=70)).isoformat()
    return (quarter_end + timedelta(days=120)).isoformat()


def build_evidence_pack(validated: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    metrics = validated["validated_metrics"]
    compact_facts = build_compact_facts(validated)
    return {
        "schema_version": "web-runner-evidence-pack-v1",
        "ticker": validated["ticker"],
        "company_name": validated["company_name"],
        "analysis_date": validated["analysis_date"],
        "currency": validated["currency"],
        "compact_facts": compact_facts,
        "facts": [
            {
                "key": key,
                "value": value.get("value"),
                "grade": value.get("grade"),
                "tag": value.get("display_tag"),
                "sources": value.get("sources", []),
            }
            for key, value in metrics.items()
        ],
        "scenario_anchors": validated.get("scenario_anchors") or {},
        "timeline_events": validated.get("timeline_events") or {},
        "sanity_alerts": validated.get("sanity_alerts") or [],
        "raw_artifacts": [{"type": "yfinance_raw", "source": raw.get("data_source")}],
        "raw_access_policy": {"allowed_reasons": []},
        "_sanitization": {"status": "trusted_generated_artifact"},
    }


def build_compact_facts(validated: dict[str, Any]) -> list[str]:
    metrics = validated["validated_metrics"]
    currency = validated.get("currency") or "USD"

    def value(key: str) -> Any:
        metric_item = metrics.get(key) if isinstance(metrics.get(key), dict) else {}
        return metric_item.get("value")

    facts = [
        f"Current price {format_money(value('price'), currency)}; day change {format_pct(validated.get('price_day_change_pct'))} [Portal]",
        f"Market cap {format_money(value('market_cap'), currency, suffix='B')} with beta {format_plain(value('beta'))} [Portal]",
        f"Forward P/E {format_multiple(value('pe_forward'))}, trailing P/E {format_multiple(value('pe_trailing'))}, EV/EBITDA {format_multiple(value('ev_ebitda'))} [Portal]",
        f"TTM revenue {format_money(value('revenue_ttm'), currency, suffix='B')}; latest-quarter revenue growth {format_pct(value('revenue_growth_yoy'))} [Calc]",
        f"Operating margin {format_pct(value('operating_margin'))}; net margin {format_pct(value('net_margin'))}; FCF yield {format_pct(value('fcf_yield'))} [Calc]",
        f"TTM FCF {format_money(value('fcf_ttm'), currency, suffix='B')} on capex {format_money(value('capex_ttm'), currency, suffix='B')} [Calc]",
        f"Analyst target mean {format_money(value('analyst_target_mean'), currency)}, median {format_money(value('analyst_target_median'), currency)}, high {format_money(value('analyst_target_high'), currency)}, low {format_money(value('analyst_target_low'), currency)} [Est]",
    ]
    return [fact for fact in facts if "—" not in fact[:35]]


def format_money(value: Any, currency: str, *, suffix: str = "") -> str:
    number = as_number(value)
    symbol = "$" if currency == "USD" else ("₩" if currency == "KRW" else f"{currency} ")
    return f"{symbol}{number:,.2f}{suffix}" if number is not None else "—"


def format_pct(value: Any) -> str:
    number = as_number(value)
    return f"{number:+.2f}%" if number is not None else "—"


def format_multiple(value: Any) -> str:
    number = as_number(value)
    return f"{number:.1f}x" if number is not None else "—"


def format_plain(value: Any) -> str:
    number = as_number(value)
    return f"{number:.2f}" if number is not None else "—"


def build_context_budget(validated: dict[str, Any]) -> dict[str, Any]:
    fact_count = len(validated.get("validated_metrics", {}))
    return {
        "schema_version": "web-runner-context-budget-v1",
        "totals": {
            "estimated_input_tokens": 1200 + fact_count * 80,
            "within_soft_limit": True,
        },
        "routing": {"logical_tier": "analyst_main"},
    }


def run_analyst(
    *,
    evidence_pack: dict[str, Any],
    language: str,
    mode: str,
    ticker: str,
    validated: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    backend_name = os.environ.get("ANALYST_BACKEND", "openai_api")
    backend = get_backend(backend_name, logical_tier="analyst_main")
    system = build_system_prompt(language)
    user = {
        "role": "user",
        "content": json.dumps(
            {
                "task": "Create a Mode A investment briefing analysis-result JSON.",
                "ticker": ticker,
                "mode": mode,
                "language": language,
                "validated_data": validated,
                "evidence_pack": evidence_pack,
                "rules": [
                    "Do not fabricate numbers.",
                    "Every numeric claim must use provided facts or be labeled as an estimate.",
                    "Grade D data must be omitted or shown as null.",
                    "Use evidence_pack.scenario_anchors.scenarios exactly for bull/base/bear targets, return_pct, and probabilities.",
                    "Use evidence_pack.scenario_anchors.rr_score exactly for rr_score.",
                    "Use evidence_pack.timeline_events.past and future as the event timeline; do not replace them with 'evidence unavailable' placeholders.",
                    "Include at least 3 past timeline events and 2 future events.",
                    "Avoid generic 'insufficient evidence' filler. If evidence is thin, make the limitation a single quality note, not the body of the report.",
                    "The one-line thesis, risk, and action signal must be company-specific and tied to valuation, latest-quarter growth, FCF yield, and analyst target spread.",
                ],
            },
            ensure_ascii=False,
        ),
    }
    result = backend.complete(
        system=system,
        messages=[user],
        json_schema=analysis_schema(),
        max_tokens=3500,
    )
    if not result.json:
        raise PipelineError("analyst backend did not return JSON")
    return result.json, {
        "provider": result.provider,
        "model": result.model,
        "usage": result.usage,
    }


def build_system_prompt(language: str) -> str:
    lang = "Korean" if language == "ko" else "English"
    return (
        "You are an institutional-grade stock analyst. Produce only JSON that "
        "matches the provided schema. Blank is better than wrong. No source, no "
        "number. Keep statements company-specific. Include causal risk chains. "
        "A report with null scenario targets, null R/R score, or repeated "
        "evidence-unavailable language is a failed report. "
        f"Write human-readable fields in {lang}."
    )


def analysis_schema() -> dict[str, Any]:
    metric_schema = {
        "type": "object",
        "properties": {
            "value": {"type": ["number", "string", "null"]},
            "unit": {"type": ["string", "null"]},
            "grade": {"type": "string"},
            "display_tag": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["value", "unit", "grade", "display_tag", "sources"],
        "additionalProperties": True,
    }
    event_schema = {
        "type": "object",
        "properties": {
            "date": {"type": "string"},
            "event": {"type": "string"},
            "significance": {"type": "string"},
            "narrative": {"type": "string"},
        },
        "required": ["date", "event", "significance", "narrative"],
        "additionalProperties": False,
    }
    scenario_schema = {
        "type": "object",
        "properties": {
            "target": {"type": ["number", "null"]},
            "return_pct": {"type": ["number", "null"]},
            "probability": {"type": ["number", "null"]},
            "key_assumption": {"type": "string"},
        },
        "required": ["target", "return_pct", "probability", "key_assumption"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string"},
            "rr_score": {"type": ["number", "null"]},
            "rr_score_interpretation": {"type": "string"},
            "key_metrics": {
                "type": "object",
                "additionalProperties": metric_schema,
            },
            "scenarios": {
                "type": "object",
                "properties": {
                    "bull": scenario_schema,
                    "base": scenario_schema,
                    "bear": scenario_schema,
                },
                "required": ["bull", "base", "bear"],
                "additionalProperties": False,
            },
            "top_risks": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "risk": {"type": "string"},
                        "mechanism": {"type": "string"},
                    },
                    "required": ["risk", "mechanism"],
                    "additionalProperties": True,
                },
            },
            "upcoming_catalysts": {
                "type": "array",
                "minItems": 1,
                "items": event_schema,
            },
            "thesis_pillars": {
                "type": "array",
                "minItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "pillar": {"type": "string"},
                        "current_status": {"type": "string"},
                        "trend": {"type": "string"},
                        "latest_evidence": {"type": "string"},
                    },
                    "required": ["pillar", "current_status", "trend", "latest_evidence"],
                    "additionalProperties": False,
                },
            },
            "sections": {
                "type": "object",
                "properties": {
                    "one_line_thesis": {"type": "string"},
                    "action_signal": {"type": "string"},
                    "timeline_past": {"type": "array", "items": event_schema},
                    "timeline_future": {"type": "array", "items": event_schema},
                    "pattern_detection": {"type": "string"},
                },
                "required": [
                    "one_line_thesis",
                    "action_signal",
                    "timeline_past",
                    "timeline_future",
                    "pattern_detection",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "verdict",
            "rr_score",
            "rr_score_interpretation",
            "key_metrics",
            "scenarios",
            "top_risks",
            "upcoming_catalysts",
            "thesis_pillars",
            "sections",
        ],
        "additionalProperties": True,
    }


def enrich_analysis_result(
    analyst_json: dict[str, Any],
    *,
    backend_meta: dict[str, Any],
    language: str,
    mode: str,
    paths: dict[str, Path],
    ticker: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    metrics = validated["validated_metrics"]
    scenario_anchors = validated.get("scenario_anchors") or {}
    anchored_scenarios = scenario_anchors.get("scenarios")
    anchored_rr_score = scenario_anchors.get("rr_score")
    analysis = dict(analyst_json)
    if isinstance(anchored_scenarios, dict) and anchored_scenarios:
        analysis["scenarios"] = anchored_scenarios
    if anchored_rr_score is not None:
        analysis["rr_score"] = anchored_rr_score
        analysis["rr_score_interpretation"] = rr_interpretation(anchored_rr_score)
    analysis["verdict"] = verdict_from_rr(anchored_rr_score)
    analysis.update(
        {
            "ticker": ticker,
            "company_name": validated["company_name"],
            "exchange": "KRX" if validated["market"] == "KR" else "NASDAQ/NYSE",
            "market": validated["market"],
            "company_type": validated.get("company_type"),
            "data_mode": "standard",
            "requested_mode": "standard",
            "effective_mode": "standard",
            "source_profile": validated["source_profile"],
            "source_tier": validated["source_tier"],
            "confidence_cap": validated["confidence_cap"],
            "output_mode": mode,
            "output_language": language,
            "analysis_date": validated["analysis_date"],
            "price_at_analysis": metric_value(metrics, "price"),
            "price_day_change": validated.get("price_day_change"),
            "price_day_change_pct": validated.get("price_day_change_pct"),
            "currency": validated["currency"],
            "report_path": str(paths["reports_dir"].relative_to(REPO_ROOT)),
            "run_context": {
                "run_id": paths["ticker_root"].parent.name,
                "backend": backend_meta,
                "generated_by": "scripts/run_analysis.py",
            },
            "data_quality_used": {"overall_grade": validated["overall_grade"]},
            "data_confidence_summary": validated["overall_grade"],
            "_sanitization": {"status": "trusted_generated_artifact"},
        }
    )
    analysis["key_metrics"] = select_key_metrics(metrics)
    normalize_timeline_from_validated(analysis, validated)
    return analysis


def rr_interpretation(rr_score: Any) -> str:
    score = as_number(rr_score)
    if score is None:
        return "Unavailable: scenario downside could not be quantified."
    if score > 3:
        return "Attractive: expected upside materially exceeds probability-weighted downside."
    if score >= 1:
        return "Balanced: upside exists, but not enough for a full-position signal."
    return "Unfavorable: downside dominates the current quick scenario set."


def verdict_from_rr(rr_score: Any) -> str:
    score = as_number(rr_score)
    if score is None:
        return "중립"
    if score > 3:
        return "비중확대"
    if score >= 1:
        return "관찰"
    return "비중축소"


def normalize_timeline_from_validated(analysis: dict[str, Any], validated: dict[str, Any]) -> None:
    timeline = validated.get("timeline_events") if isinstance(validated.get("timeline_events"), dict) else {}
    sections = analysis.setdefault("sections", {})
    if not isinstance(sections, dict):
        sections = {}
        analysis["sections"] = sections
    past = timeline.get("past")
    future = timeline.get("future")
    if isinstance(past, list) and len(sections.get("timeline_past") or []) < 3:
        sections["timeline_past"] = past
    if isinstance(future, list) and len(sections.get("timeline_future") or []) < 2:
        sections["timeline_future"] = future


def metric_value(metrics: dict[str, Any], key: str) -> Any:
    metric_item = metrics.get(key)
    return metric_item.get("value") if isinstance(metric_item, dict) else None


def select_key_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    selected = {}
    for key in ["pe_forward", "revenue_growth_yoy", "fcf_yield"]:
        if key in metrics:
            selected[key] = metrics[key]
    if len(selected) < 3 and "price" in metrics:
        selected["price"] = metrics["price"]
    return selected


def validate_analysis_result(analysis: dict[str, Any]) -> None:
    missing = [
        key
        for key in ["ticker", "output_mode", "analysis_date", "verdict", "sections"]
        if key not in analysis
    ]
    if missing:
        raise PipelineError(f"analysis-result missing required fields: {missing}")
    sections = analysis.get("sections")
    if not isinstance(sections, dict):
        raise PipelineError("analysis-result.sections must be an object")
    if len(sections.get("timeline_past") or []) < 1:
        raise PipelineError("Mode A requires at least one past timeline event")
    if len(sections.get("timeline_future") or []) < 1:
        raise PipelineError("Mode A requires at least one future timeline event")
    scenarios = analysis.get("scenarios")
    if not isinstance(scenarios, dict):
        raise PipelineError("Mode A requires quantified scenarios")
    for scenario_name in ["bull", "base", "bear"]:
        scenario = scenarios.get(scenario_name)
        if not isinstance(scenario, dict):
            raise PipelineError(f"Mode A missing {scenario_name} scenario")
        for key in ["target", "return_pct", "probability"]:
            if as_number(scenario.get(key)) is None:
                raise PipelineError(f"Mode A {scenario_name}.{key} must be numeric")
    probabilities = sum(
        as_number(scenarios[name].get("probability")) or 0 for name in ["bull", "base", "bear"]
    )
    if abs(probabilities - 1.0) > 0.02:
        raise PipelineError("Mode A scenario probabilities must sum to 100%")
    if as_number(analysis.get("rr_score")) is None:
        raise PipelineError("Mode A requires a numeric R/R score")
    if len(sections.get("timeline_past") or []) < 3:
        raise PipelineError("Mode A requires at least three past timeline events")
    if len(sections.get("timeline_future") or []) < 2:
        raise PipelineError("Mode A requires at least two future timeline events")
    serialized = json.dumps(analysis, ensure_ascii=False).lower()
    weak_markers = [
        "evidence unavailable",
        "provided data",
        "근거 부족",
        "증거 부족",
        "date tbd",
        "no dated catalyst",
    ]
    marker_hits = sum(serialized.count(marker) for marker in weak_markers)
    if marker_hits > 2:
        raise PipelineError("Mode A analysis is too evidence-thin for publication")


def render_mode_a(input_path: Path, output_path: Path) -> None:
    command = [
        sys.executable,
        ".claude/skills/briefing-generator/scripts/render-briefing.py",
        "--input",
        str(input_path.relative_to(REPO_ROOT)),
        "--output",
        str(output_path.relative_to(REPO_ROOT)),
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PipelineError((result.stderr or result.stdout or "render failed")[-2000:])


def run_quality_gate(report_path: Path, *, min_bytes: int = 20_000) -> None:
    if not report_path.exists():
        raise PipelineError("report HTML was not written")
    html = report_path.read_text(encoding="utf-8", errors="replace")
    if report_path.stat().st_size < min_bytes:
        raise PipelineError("HTML report is suspiciously small.")
    if "arrays not present in this fixture" in html:
        raise PipelineError("Eval-only renderer output detected.")
    if "/Users/" in html or "stock-analysis-agent/output" in html:
        raise PipelineError("Local path leaked into HTML report.")
    if "investment advice" not in html.lower():
        raise PipelineError("Disclaimer missing from report HTML.")


def build_quality_report(analysis: dict[str, Any], report_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "web-runner-quality-report-v1",
        "ticker": analysis["ticker"],
        "output_mode": analysis["output_mode"],
        "status": "passed",
        "checks": {
            "html_min_size": True,
            "no_eval_marker": True,
            "no_local_path_leak": True,
            "disclaimer_present": True,
        },
        "report_path": str(report_path.relative_to(REPO_ROOT)),
        "created_at": utc_now(),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
