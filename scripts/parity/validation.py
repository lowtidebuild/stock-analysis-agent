"""Validation and compact handoff builders for the A/B/C parity runner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.artifact_validation import (
    build_validated_data_sanity_flags,
    validate_artifact_data,
)
from tools.context_budget import build_context_budget
from tools.evidence_pack import build_evidence_pack

from scripts.parity.data_sources import load_json, write_json

REPO_ROOT = Path(__file__).resolve().parents[2]

CORE_METRICS = (
    "price_at_analysis",
    "market_cap",
    "pe_ratio",
    "pe_forward",
    "ev_ebitda",
    "pb_ratio",
    "revenue_ttm",
    "revenue_growth_yoy",
    "operating_margin",
    "net_margin",
    "fcf_ttm",
    "fcf_yield",
    "net_debt",
    "net_debt_ebitda",
    "diluted_shares",
    "analyst_target_mean",
)

GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}
NON_MONETARY_TIER2_METRICS = {
    "pe_ratio",
    "pe_forward",
    "ev_ebitda",
    "pb_ratio",
    "revenue_growth_yoy",
    "operating_margin",
    "net_margin",
    "fcf_yield",
    "net_debt_ebitda",
    "beta",
}


@dataclass(frozen=True)
class ValidationResult:
    ticker: str
    artifact_root: Path
    validated_data_path: Path
    evidence_pack_path: Path
    context_budget_path: Path
    validation_summary_path: Path
    overall_grade: str
    fact_count: int
    excluded_count: int


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_part(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def build_validation_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> ValidationResult:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    run_dir = ticker_dir.parent
    macro_path = run_dir / "macro" / "fred-raw.json"
    raw_paths = {
        "financial_datasets": ticker_dir / "financial-datasets-raw.json",
        "dart": ticker_dir / "dart-api-raw.json",
        "yfinance": ticker_dir / "yfinance-raw.json",
        "tier2": ticker_dir / "tier2-raw.json",
        "fred": macro_path,
    }
    raw_payloads = {
        source: load_json(path) if path.exists() else {}
        for source, path in raw_paths.items()
    }

    validated = build_validated_data(
        language=language,
        market=market,
        mode=mode,
        raw_payloads=raw_payloads,
        run_id=run_id,
        ticker=ticker,
        ticker_dir=ticker_dir,
    )
    validated_path = ticker_dir / "validated-data.json"
    write_json(validated_path, validated)

    raw_refs = [
        display_path(path)
        for path in raw_paths.values()
        if path.exists()
    ]
    evidence_pack = build_evidence_pack(validated, raw_artifact_refs=raw_refs)
    evidence_path = ticker_dir / "evidence-pack.json"
    write_json(evidence_path, evidence_pack)

    context_budget = build_context_budget(run_dir, ticker=ticker)
    context_path = ticker_dir / "context-budget.json"
    write_json(context_path, context_budget)

    validation_errors = {
        "validated_data": validate_artifact_data("validated-data", validated),
        "evidence_pack": validate_artifact_data("evidence-pack", evidence_pack),
        "context_budget": validate_artifact_data("context-budget", context_budget),
    }
    if raw_paths["tier2"].exists():
        validation_errors["tier2_raw"] = validate_artifact_data("tier2-raw", raw_payloads["tier2"])
    blocking_errors = [
        f"{artifact}: {error}"
        for artifact, errors in validation_errors.items()
        for error in errors
    ]
    summary = {
        "schema_version": "abc-parity-validation-summary-v1",
        "ticker": ticker,
        "market": market,
        "mode": mode,
        "language": language,
        "overall_grade": validated["overall_grade"],
        "grade_summary": validated["grade_summary"],
        "fact_count": len(evidence_pack["facts"]),
        "excluded_count": len(evidence_pack["exclusions"]),
        "blocking_errors": blocking_errors,
        "created_at": utc_now(),
        "artifacts": {
            "validated_data": display_path(validated_path),
            "evidence_pack": display_path(evidence_path),
            "context_budget": display_path(context_path),
        },
    }
    summary_path = ticker_dir / "validation-summary.json"
    write_json(summary_path, summary)
    if blocking_errors:
        raise ValueError(
            "validation handoff failed contract checks: " + "; ".join(blocking_errors[:5])
        )

    return ValidationResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        validated_data_path=validated_path,
        evidence_pack_path=evidence_path,
        context_budget_path=context_path,
        validation_summary_path=summary_path,
        overall_grade=validated["overall_grade"],
        fact_count=len(evidence_pack["facts"]),
        excluded_count=len(evidence_pack["exclusions"]),
    )


def build_validated_data(
    *,
    language: str,
    market: str,
    mode: str,
    raw_payloads: dict[str, dict[str, Any]],
    run_id: str,
    ticker: str,
    ticker_dir: Path,
) -> dict[str, Any]:
    financial = raw_payloads.get("financial_datasets") or {}
    dart = raw_payloads.get("dart") or {}
    yfinance = raw_payloads.get("yfinance") or {}
    tier2 = raw_payloads.get("tier2") or {}
    fred = raw_payloads.get("fred") or {}
    source_profile = choose_source_profile(market=market, financial=financial, dart=dart, yfinance=yfinance)
    profile_meta = source_profile_meta(source_profile)
    currency = infer_currency(market=market, yfinance=yfinance, dart=dart)
    company_name = infer_company_name(ticker=ticker, yfinance=yfinance, dart=dart, financial=financial)

    metrics: dict[str, dict[str, Any]] = {}
    metric_conflicts: list[dict[str, Any]] = metric_conflicts_from_tier2(tier2)
    if source_profile == "financial_datasets":
        metrics.update(metrics_from_financial_datasets(financial, ticker=ticker, currency=currency))
    elif source_profile == "sec_or_dart_primary":
        metrics.update(metrics_from_dart(dart, yfinance=yfinance, currency=currency))

    metrics.update(
        merge_missing_metrics(
            current=metrics,
            fallback=metrics_from_yfinance(yfinance, market=market, currency=currency),
        )
    )
    metrics.update(
        merge_missing_metrics(
            current=metrics,
            fallback=metrics_from_tier2(tier2, market=market, currency=currency),
        )
    )
    metrics = fill_core_metric_exclusions(metrics)
    grade_summary = summarize_grades(metrics)
    exclusions = build_exclusions(metrics)
    overall_grade = determine_overall_grade(
        grade_summary=grade_summary,
        confidence_cap=profile_meta["confidence_cap"],
        source_profile=source_profile,
    )
    validation_timestamp = utc_now()
    macro_context = build_macro_context(fred, tier2=tier2)
    source_registry = build_source_registry(raw_payloads)
    staleness = build_staleness(metrics, validation_timestamp)
    validation_payload = {
        "schema_version": "abc-parity-validated-data-v1",
        "ticker": ticker,
        "market": market,
        "company_name": company_name,
        "analysis_date": validation_timestamp[:10],
        "output_mode": mode,
        "output_language": language,
        "data_mode": "enhanced",
        "requested_mode": "enhanced",
        "effective_mode": profile_meta["effective_mode"],
        "source_profile": source_profile,
        "source_tier": profile_meta["source_tier"],
        "confidence_cap": profile_meta["confidence_cap"],
        "validation_timestamp": validation_timestamp,
        "overall_grade": overall_grade,
        "currency": currency,
        "run_context": {
            "run_id": run_id,
            "artifact_root": display_path(ticker_dir),
            "ticker": ticker,
        },
        "metrics": metrics,
        "validated_metrics": metrics,
        "financials_quarterly": extract_quarterly_rows(financial=financial, yfinance=yfinance),
        "valuation_inputs": build_valuation_inputs(metrics),
        "source_registry": source_registry,
        "exclusions": exclusions,
        "conflicts": metric_conflicts,
        "metric_conflicts": metric_conflicts,
        "staleness": staleness,
        "macro_context": macro_context,
        "grade_summary": grade_summary,
        "_validation": {
            "runner": "scripts/parity/validation.py",
            "sanity_flags": build_validated_data_sanity_flags({"validated_metrics": metrics}),
            "blank_over_wrong": True,
        },
    }
    return validation_payload


def choose_source_profile(
    *,
    market: str,
    financial: dict[str, Any],
    dart: dict[str, Any],
    yfinance: dict[str, Any],
) -> str:
    if market == "US" and has_successful_source(financial):
        return "financial_datasets"
    if market == "KR" and has_successful_source(dart):
        return "sec_or_dart_primary"
    if has_successful_source(yfinance):
        return "yfinance_fallback"
    return "web_only"


def source_profile_meta(source_profile: str) -> dict[str, str]:
    if source_profile == "financial_datasets":
        return {
            "effective_mode": "enhanced",
            "source_tier": "api_structured",
            "confidence_cap": "A",
        }
    if source_profile == "sec_or_dart_primary":
        return {
            "effective_mode": "enhanced",
            "source_tier": "filing_primary",
            "confidence_cap": "A",
        }
    if source_profile == "yfinance_fallback":
        return {
            "effective_mode": "standard",
            "source_tier": "portal_structured",
            "confidence_cap": "C",
        }
    return {
        "effective_mode": "standard",
        "source_tier": "search_snippet",
        "confidence_cap": "C",
    }


def has_successful_source(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("api_status") or "").lower()
    if status in {"success", "partial", "cached", "stale_cache"}:
        return True
    if payload.get("calls_succeeded"):
        return True
    if payload.get("confidence_grade") in {"A", "B", "C"}:
        return True
    if isinstance(payload.get("ttm_income_statement"), dict) or isinstance(payload.get("balance_sheet_latest"), dict):
        return True
    current_price = payload.get("current_price")
    if isinstance(current_price, dict) and as_number(current_price.get("price")) is not None:
        return True
    return False


def metrics_from_yfinance(
    yfinance: dict[str, Any],
    *,
    currency: str,
    market: str,
) -> dict[str, dict[str, Any]]:
    if not has_successful_source(yfinance):
        return {}

    price = yfinance.get("current_price") if isinstance(yfinance.get("current_price"), dict) else {}
    info = yfinance.get("info") if isinstance(yfinance.get("info"), dict) else {}
    derived = yfinance.get("derived_ttm") if isinstance(yfinance.get("derived_ttm"), dict) else {}
    analyst_targets = yfinance.get("analyst_targets") if isinstance(yfinance.get("analyst_targets"), dict) else {}
    income_rows = yfinance.get("income_statements") if isinstance(yfinance.get("income_statements"), list) else []
    cashflow_rows = yfinance.get("cash_flow_statements") if isinstance(yfinance.get("cash_flow_statements"), list) else []
    balance_rows = yfinance.get("balance_sheets") if isinstance(yfinance.get("balance_sheets"), list) else []
    latest_balance = first_dict(balance_rows)
    source_type = "portal_kr" if market == "KR" else "portal_global"
    tag = "[KR-Portal]" if market == "KR" else "[Portal]"
    as_of = date_part(price.get("as_of") or yfinance.get("collection_timestamp"))

    market_cap = as_number(info.get("market_cap"))
    revenue_ttm = as_number(derived.get("revenue_ttm") or info.get("total_revenue"))
    operating_income_ttm = as_number(derived.get("operating_income_ttm"))
    net_income_ttm = as_number(derived.get("net_income_ttm") or info.get("net_income_to_common"))
    fcf_ttm = as_number(derived.get("fcf_ttm") or info.get("free_cashflow"))
    operating_cashflow_ttm = sum_recent(cashflow_rows, "operating_cashflow", 4)
    capex_ttm = sum_recent(cashflow_rows, "capital_expenditure", 4)
    total_debt = as_number(latest_balance.get("total_debt") or info.get("total_debt"))
    cash = as_number(latest_balance.get("cash_and_equivalents") or info.get("total_cash"))
    net_debt = safe_subtract(total_debt, cash)
    implied_ebitda = safe_div(info.get("enterprise_value"), info.get("ev_ebitda"))
    shares_outstanding = as_number(info.get("shares_outstanding"))

    return {
        "price_at_analysis": metric(
            price.get("price"),
            currency=currency,
            grade="C",
            source=f"yfinance {price.get('source_field') or 'current_price'}",
            source_type=source_type,
            tag=tag,
            as_of_date=as_of,
        ),
        "market_cap": metric(
            billions(market_cap),
            currency=currency,
            grade="C",
            source="yfinance marketCap",
            source_type=source_type,
            tag=tag,
            unit="billions",
            as_of_date=as_of,
        ),
        "pe_ratio": metric(info.get("pe_trailing"), grade="C", source="yfinance trailingPE", source_type=source_type, tag=tag, unit="x", as_of_date=as_of),
        "pe_forward": metric(info.get("pe_forward"), grade="C", source="yfinance forwardPE", source_type=source_type, tag=tag, unit="x", as_of_date=as_of),
        "ev_ebitda": metric(info.get("ev_ebitda"), grade="C", source="yfinance enterpriseToEbitda", source_type=source_type, tag=tag, unit="x", as_of_date=as_of),
        "pb_ratio": metric(info.get("pb_ratio"), grade="C", source="yfinance priceToBook", source_type=source_type, tag=tag, unit="x", as_of_date=as_of),
        "revenue_ttm": metric(billions(revenue_ttm), currency=currency, grade="C", source="yfinance trailing four quarters", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=latest_period(income_rows)),
        "revenue_growth_yoy": metric(quarter_yoy_growth(income_rows, "revenue"), grade="C", source="yfinance latest quarter vs year-ago quarter", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=latest_period(income_rows)),
        "operating_margin": metric(safe_pct(operating_income_ttm, revenue_ttm), grade="C", source="calculated operating income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=latest_period(income_rows)),
        "net_margin": metric(safe_pct(net_income_ttm, revenue_ttm), grade="C", source="calculated net income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=latest_period(income_rows)),
        "fcf_ttm": metric(billions(fcf_ttm), currency=currency, grade="C", source="yfinance trailing four quarters", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=latest_period(cashflow_rows)),
        "fcf_yield": metric(safe_pct(fcf_ttm, market_cap), grade="C", source="calculated FCF / market cap", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of),
        "operating_cashflow_ttm": metric(billions(operating_cashflow_ttm), currency=currency, grade="C", source="yfinance trailing four quarters", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=latest_period(cashflow_rows)),
        "capex_ttm": metric(billions(capex_ttm), currency=currency, grade="C", source="yfinance trailing four quarters", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=latest_period(cashflow_rows)),
        "net_debt_ebitda": metric(safe_div(net_debt, implied_ebitda), grade="C", source="calculated net debt / implied EBITDA", source_type="calculated", tag="[Calc]", unit="x", as_of_date=latest_period(balance_rows)),
        "net_debt": metric(billions(net_debt), currency=currency, grade="C", source="calculated total debt - cash", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=latest_period(balance_rows)),
        "diluted_shares": metric(millions(shares_outstanding), grade="C", source="yfinance sharesOutstanding", source_type=source_type, tag=tag, unit="millions", as_of_date=as_of),
        "analyst_target_mean": metric(analyst_targets.get("mean_target"), currency=currency, grade="C", source="yfinance analyst target mean", source_type="estimate", tag="[Est]", as_of_date=as_of),
        "analyst_target_median": metric(analyst_targets.get("median_target"), currency=currency, grade="C", source="yfinance analyst target median", source_type="estimate", tag="[Est]", as_of_date=as_of),
        "analyst_target_high": metric(analyst_targets.get("high_target"), currency=currency, grade="C", source="yfinance analyst target high", source_type="estimate", tag="[Est]", as_of_date=as_of),
        "analyst_target_low": metric(analyst_targets.get("low_target"), currency=currency, grade="C", source="yfinance analyst target low", source_type="estimate", tag="[Est]", as_of_date=as_of),
        "beta": metric(info.get("beta"), grade="C", source="yfinance beta", source_type=source_type, tag=tag, as_of_date=as_of),
        "fifty_two_week_high": metric(info.get("fifty_two_week_high"), currency=currency, grade="C", source="yfinance 52-week high", source_type=source_type, tag=tag, as_of_date=as_of),
        "fifty_two_week_low": metric(info.get("fifty_two_week_low"), currency=currency, grade="C", source="yfinance 52-week low", source_type=source_type, tag=tag, as_of_date=as_of),
    }


def metrics_from_dart(
    dart: dict[str, Any],
    *,
    currency: str,
    yfinance: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if not has_successful_source(dart):
        return {}
    income = dart.get("ttm_income_statement") if isinstance(dart.get("ttm_income_statement"), dict) else {}
    ttm_precision = income.get("precision")
    ttm_note = income.get("calculation_note")
    income_grade = "A" if ttm_precision in {"high", "medium"} else "C"
    balance = dart.get("balance_sheet_latest") if isinstance(dart.get("balance_sheet_latest"), dict) else {}
    periods = dart.get("periods_detail") if isinstance(dart.get("periods_detail"), dict) else {}
    annual = periods.get("Annual") if isinstance(periods.get("Annual"), dict) else {}
    annual_metrics = annual.get("metrics") if isinstance(annual.get("metrics"), dict) else {}
    yfinance_metrics = metrics_from_yfinance(yfinance, market="KR", currency=currency)
    market_cap_value = metric_value(yfinance_metrics.get("market_cap"))
    revenue = as_number(income.get("revenue"))
    operating_income = as_number(income.get("operating_income"))
    net_income = as_number(income.get("net_income"))
    cash = as_number(balance.get("cash"))
    debt_parts = [
        balance.get("short_term_debt"),
        balance.get("current_portion_lt_debt"),
        balance.get("long_term_debt"),
        balance.get("bonds_payable"),
    ]
    total_debt = sum(as_number(item) or 0 for item in debt_parts) if any(as_number(item) is not None for item in debt_parts) else None
    net_debt = safe_subtract(total_debt, cash)
    operating_cf = metric_current(annual_metrics.get("operating_cash_flow"))
    capex = metric_current(annual_metrics.get("capex"))
    fcf = safe_subtract(operating_cf, capex)
    prior_revenue = metric_prior(annual_metrics.get("revenue"))
    revenue_growth = safe_pct(safe_subtract(revenue, prior_revenue), prior_revenue)
    as_of = dart_year_date(annual.get("year")) or date_part(dart.get("collection_timestamp"))
    fs_div_used = dart.get("fs_div_used")
    ofs_prefix = (
        "[별도(OFS) 재무 기준] "
        if isinstance(fs_div_used, list) and "OFS" in fs_div_used
        else ""
    )
    income_note = (
        str(ttm_note)
        if ttm_precision != "high" and ttm_note not in (None, "")
        else ""
    )
    income_note = f"{ofs_prefix}{income_note}".strip() or None
    basis_note = ofs_prefix.strip() or None
    annual_fcf_note = (
        f"{ofs_prefix}FY{annual.get('year')} full-year FCF (annual filing); "
        "trailing-twelve-month value not reconstructable from available periods"
    )

    return {
        "revenue_ttm": metric(billions(revenue), currency=currency, grade=income_grade, source="DART OpenAPI revenue", source_type="filing", tag="[Filing]", unit="billions", as_of_date=as_of, note=income_note),
        "revenue_growth_yoy": metric(revenue_growth, grade="A", source="DART annual revenue vs prior year", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of, note=basis_note),
        "operating_margin": metric(safe_pct(operating_income, revenue), grade=income_grade, source="DART operating income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of, note=income_note),
        "net_margin": metric(safe_pct(net_income, revenue), grade=income_grade, source="DART net income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of, note=income_note),
        "fcf_ttm": metric(billions(fcf), currency=currency, grade="A", source="DART operating cash flow - capex", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=as_of, note=annual_fcf_note),
        "fcf_yield": metric(safe_pct(fcf, (market_cap_value or 0) * 1_000_000_000), grade="C", source="DART FCF / yfinance market cap (grade = min of inputs: DART A, yfinance C)", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of, note=annual_fcf_note),
        "net_debt": metric(billions(net_debt), currency=currency, grade="A", source="DART debt minus cash", source_type="calculated", tag="[Calc]", unit="billions", as_of_date=as_of, note=basis_note),
    }


def metrics_from_financial_datasets(
    financial: dict[str, Any],
    *,
    currency: str,
    ticker: str,
) -> dict[str, dict[str, Any]]:
    if not has_successful_source(financial):
        return {}
    calls = financial.get("calls") if isinstance(financial.get("calls"), dict) else {}
    ttm_record = first_record(calls.get("financials_ttm"))
    quarterly_records = records_from_payload(calls.get("financials_quarterly"))
    price_record = latest_record(calls.get("prices_recent"))
    estimates_record = first_record(calls.get("analyst_estimates"))
    as_of = (
        date_part(price_record.get("date") or price_record.get("time") or financial.get("collection_timestamp"))
        if isinstance(price_record, dict)
        else date_part(financial.get("collection_timestamp"))
    )
    revenue = pick_number(ttm_record, "revenue", "total_revenue", "sales")
    operating_income = pick_number(ttm_record, "operating_income", "operatingIncome")
    net_income = pick_number(ttm_record, "net_income", "netIncome")
    fcf = pick_number(ttm_record, "free_cash_flow", "freeCashFlow", "fcf")
    market_cap = pick_number(price_record, "market_cap", "marketCap")
    price = pick_number(price_record, "close", "price", "adj_close")
    diluted_shares = pick_number(ttm_record, "diluted_shares", "weighted_average_shares", "shares_diluted")
    if diluted_shares is None and market_cap and price:
        diluted_shares = market_cap / price
    pe = pick_number(ttm_record, "pe_ratio", "price_to_earnings", "p_e")
    ev_ebitda = pick_number(ttm_record, "ev_ebitda", "enterprise_value_to_ebitda")
    pb = pick_number(ttm_record, "pb_ratio", "price_to_book")
    revenue_growth = growth_from_quarters(quarterly_records, "revenue")

    return {
        "price_at_analysis": metric(price, currency=currency, grade="C", source=f"Financial Datasets prices for {ticker}", source_type="portal_global", tag="[Portal]", as_of_date=as_of),
        "market_cap": metric(billions(market_cap), currency=currency, grade="C", source="Financial Datasets market cap", source_type="portal_global", tag="[Portal]", unit="billions", as_of_date=as_of),
        "pe_ratio": metric(pe, grade="B", source="Financial Datasets TTM financials", source_type="filing", tag="[Filing]", unit="x", as_of_date=as_of),
        "ev_ebitda": metric(ev_ebitda, grade="B", source="Financial Datasets TTM financials", source_type="filing", tag="[Filing]", unit="x", as_of_date=as_of),
        "pb_ratio": metric(pb, grade="B", source="Financial Datasets TTM financials", source_type="filing", tag="[Filing]", unit="x", as_of_date=as_of),
        "revenue_ttm": metric(billions(revenue), currency=currency, grade="A", source="Financial Datasets TTM revenue", source_type="filing", tag="[Filing]", unit="billions", as_of_date=as_of),
        "revenue_growth_yoy": metric(revenue_growth, grade="B", source="Financial Datasets quarterly revenue YoY", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of),
        "operating_margin": metric(safe_pct(operating_income, revenue), grade="A", source="Financial Datasets operating income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of),
        "net_margin": metric(safe_pct(net_income, revenue), grade="A", source="Financial Datasets net income / revenue", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of),
        "fcf_ttm": metric(billions(fcf), currency=currency, grade="A", source="Financial Datasets free cash flow", source_type="filing", tag="[Filing]", unit="billions", as_of_date=as_of),
        "fcf_yield": metric(safe_pct(fcf, market_cap), grade="B", source="Financial Datasets FCF / market cap", source_type="calculated", tag="[Calc]", unit="percent", as_of_date=as_of),
        "diluted_shares": metric(millions(diluted_shares), grade="B", source="Financial Datasets diluted shares or market cap / price", source_type="calculated", tag="[Calc]", unit="millions", as_of_date=as_of),
        "analyst_target_mean": metric(pick_number(estimates_record, "target_mean", "mean_target", "price_target"), currency=currency, grade="B", source="Financial Datasets analyst estimates", source_type="estimate", tag="[Est]", as_of_date=as_of),
    }


def metrics_from_tier2(
    tier2: dict[str, Any],
    *,
    currency: str,
    market: str,
) -> dict[str, dict[str, Any]]:
    candidates = tier2.get("extracted_metric_candidates")
    if not isinstance(candidates, list):
        return {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        metric_name = str(candidate.get("metric") or "").strip()
        if not metric_name:
            continue
        grouped.setdefault(metric_name, []).append(candidate)

    metrics: dict[str, dict[str, Any]] = {}
    for metric_name, metric_candidates in grouped.items():
        selected = sorted(metric_candidates, key=tier2_candidate_sort_key)[0]
        entry = metric_from_tier2_candidate(
            metric_name,
            selected,
            currency=currency,
            market=market,
        )
        if entry is not None:
            metrics[metric_name] = entry
    return metrics


def tier2_candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    grade = str(candidate.get("confidence_candidate") or "D").upper()
    rank = as_number(candidate.get("source_result_rank"))
    return (
        grade_rank.get(grade, 3),
        int(rank) if rank is not None and rank >= 1 else 999,
        str(candidate.get("candidate_id") or ""),
    )


def metric_from_tier2_candidate(
    metric_name: str,
    candidate: dict[str, Any],
    *,
    currency: str,
    market: str,
) -> dict[str, Any] | None:
    value = as_number(candidate.get("normalized_value"))
    if value is None:
        return None

    candidate_grade = str(candidate.get("confidence_candidate") or "D").upper()
    if candidate_grade not in {"A", "B", "C"}:
        return None
    grade = "C" if GRADE_ORDER[candidate_grade] > GRADE_ORDER["C"] else candidate_grade
    source_type = tier2_source_type(metric_name, candidate, market=market)
    candidate_currency = candidate.get("currency")
    unit = candidate.get("unit")
    if not candidate_currency and isinstance(unit, str) and unit.upper() in {"USD", "KRW"}:
        candidate_currency = unit.upper()
        unit = None
    source = candidate.get("source_url") or candidate.get("source_domain") or "tier2 web research candidate"
    metric_currency = tier2_metric_currency(
        metric_name,
        candidate_currency=candidate_currency,
        fallback_currency=currency,
    )
    entry = metric(
        value,
        currency=metric_currency,
        grade=grade,
        source=f"tier2 web candidate: {source}",
        source_type=source_type,
        tag=tier2_display_tag(source_type, market=market),
        unit=str(unit) if unit not in (None, "") else None,
        as_of_date=date_part(candidate.get("as_of_date")),
    )
    if entry.get("grade") == "D":
        return None
    source_query_id = candidate.get("source_query_id")
    entry["candidate_trace"] = {
        "selected_candidate_id": candidate.get("candidate_id"),
        "source_query_ids": [source_query_id] if source_query_id else [],
        "selection_reason": "selected from sanitized tier2 extracted_metric_candidates",
    }
    if candidate.get("notes"):
        entry["notes"] = str(candidate["notes"])
    if date_part(candidate.get("period_end")):
        entry["period_end"] = date_part(candidate.get("period_end"))
    return entry


def tier2_metric_currency(
    metric_name: str,
    *,
    candidate_currency: Any,
    fallback_currency: str,
) -> str | None:
    if candidate_currency:
        return str(candidate_currency)
    if metric_name in NON_MONETARY_TIER2_METRICS:
        return None
    monetary_markers = ("price", "target", "market_cap", "revenue", "fcf", "debt", "cash", "income", "capex")
    if any(marker in metric_name.lower() for marker in monetary_markers):
        return fallback_currency
    return None


def tier2_source_type(metric_name: str, candidate: dict[str, Any], *, market: str) -> str:
    method = str(candidate.get("extraction_method") or "").strip()
    lowered_metric = metric_name.lower()
    if lowered_metric.startswith("analyst_") or "target" in lowered_metric:
        return "estimate"
    if method == "filing_table":
        return "filing"
    if method == "calculated":
        return "calculated"
    if method == "api_structured":
        return "portal_kr" if market == "KR" else "portal_global"
    return "portal_kr" if market == "KR" else "portal_global"


def tier2_display_tag(source_type: str, *, market: str) -> str:
    if source_type == "estimate":
        return "[Est]"
    if source_type == "filing":
        return "[Filing]"
    if source_type == "calculated":
        return "[Calc]"
    return "[KR-Portal]" if market == "KR" else "[Portal]"


def metric_conflicts_from_tier2(tier2: dict[str, Any]) -> list[dict[str, Any]]:
    conflicts = tier2.get("metric_conflicts")
    if not isinstance(conflicts, list):
        return []
    result: list[dict[str, Any]] = []
    for item in conflicts:
        if not isinstance(item, dict):
            continue
        candidates = item.get("candidates") if isinstance(item.get("candidates"), list) else []
        selected_index = as_number(item.get("selected_candidate_index"))
        selected_candidate = None
        if selected_index is not None and 0 <= int(selected_index) < len(candidates):
            selected_candidate = candidates[int(selected_index)]
        selected_id = selected_candidate.get("candidate_id") if isinstance(selected_candidate, dict) else None
        result.append(
            {
                "metric": item.get("metric"),
                "summary": item.get("resolution") or item.get("notes"),
                "candidate_count": len(candidates),
                "selected_candidate_id": selected_id,
                "source": "tier2-raw.json",
            }
        )
    return result


def metric(
    value: Any,
    *,
    grade: str,
    source: str,
    source_type: str,
    tag: str,
    as_of_date: str | None = None,
    currency: str | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    numeric = as_number(value)
    if numeric is None:
        return excluded_metric(f"Missing verified value from {source}")
    entry = {
        "value": round(numeric, 4) if isinstance(numeric, float) else numeric,
        "grade": grade,
        "source_type": source_type,
        "source_authority": source_authority(source_type),
        "display_tag": tag,
        "tag": tag,
        "sources": [source],
        "unit": unit,
        "currency": currency,
        "as_of_date": as_of_date,
    }
    if note not in (None, ""):
        entry["notes"] = note
    return entry


def excluded_metric(reason: str) -> dict[str, Any]:
    return {
        "value": None,
        "grade": "D",
        "source_type": None,
        "source_authority": None,
        "display_tag": None,
        "tag": None,
        "sources": [],
        "exclusion_reason": reason,
    }


def fill_core_metric_exclusions(metrics: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = dict(metrics)
    for metric_name in CORE_METRICS:
        result.setdefault(metric_name, excluded_metric("Not enough verified source candidates"))
    return result


def merge_missing_metrics(
    *,
    current: dict[str, dict[str, Any]],
    fallback: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    additions = {}
    for key, value in fallback.items():
        existing = current.get(key)
        if existing is None or existing.get("grade") == "D":
            additions[key] = value
    return additions


def source_authority(source_type: str | None) -> str | None:
    return {
        "filing": "regulatory",
        "company_release": "issuer",
        "portal_global": "market_portal",
        "portal_kr": "market_portal",
        "calculated": "derived",
        "estimate": "sell_side",
        "macro": "government",
        "internal": "internal",
    }.get(source_type or "")


def summarize_grades(metrics: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary = {"A": 0, "B": 0, "C": 0, "D": 0}
    for entry in metrics.values():
        grade = entry.get("grade") if isinstance(entry, dict) else "D"
        if grade in summary:
            summary[grade] += 1
    return summary


def build_exclusions(metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    exclusions = []
    for name, entry in metrics.items():
        if not isinstance(entry, dict) or entry.get("grade") != "D":
            continue
        exclusions.append(
            {
                "metric": name,
                "reason": entry.get("exclusion_reason") or "Metric excluded by blank-over-wrong rule",
                "display": "—",
            }
        )
    return exclusions


def determine_overall_grade(
    *,
    confidence_cap: str,
    grade_summary: dict[str, int],
    source_profile: str,
) -> str:
    verified = grade_summary.get("A", 0) + grade_summary.get("B", 0) + grade_summary.get("C", 0)
    if verified == 0:
        candidate = "D"
    elif source_profile in {"financial_datasets", "sec_or_dart_primary"} and verified >= 6:
        candidate = "B"
    elif verified >= 4:
        candidate = "C"
    else:
        candidate = "D"
    return candidate if GRADE_ORDER[candidate] <= GRADE_ORDER[confidence_cap] else confidence_cap


def build_macro_context(fred: dict[str, Any], *, tier2: dict[str, Any] | None = None) -> dict[str, Any]:
    tier2_macro = tier2.get("macro_context") if isinstance(tier2, dict) else None
    tier2_structured = tier2_macro.get("structured") if isinstance(tier2_macro, dict) else None
    if isinstance(tier2_structured, dict):
        result = {"structured": tier2_structured}
        qualitative = tier2_macro.get("qualitative")
        if isinstance(qualitative, dict):
            result["qualitative"] = qualitative
        return result

    macro_context = fred.get("macro_context") if isinstance(fred.get("macro_context"), dict) else None
    structured = macro_context.get("structured") if isinstance(macro_context, dict) else None
    if isinstance(structured, dict):
        return {"structured": structured}
    reason = fred.get("reason") or "macro_source_unavailable"
    return {
        "structured": {
            "source": "FRED",
            "status": "unavailable",
            "grade": "D",
            "reason": reason,
            "retrieved_at": fred.get("collection_timestamp") or utc_now(),
            "series": [],
        }
    }


def build_source_registry(raw_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    registry = {}
    for source, payload in raw_payloads.items():
        status = payload.get("status") or payload.get("api_status")
        if status is None and has_successful_source(payload):
            status = "success"
        registry[source] = {
            "status": status or "missing",
            "schema_version": payload.get("schema_version"),
            "collection_timestamp": payload.get("collection_timestamp"),
            "reason": payload.get("reason"),
        }
    return registry


def build_staleness(metrics: dict[str, dict[str, Any]], validation_timestamp: str) -> dict[str, Any]:
    stale_metrics = []
    validation_date = date_part(validation_timestamp)
    for name, entry in metrics.items():
        if not isinstance(entry, dict) or entry.get("grade") == "D":
            continue
        if not entry.get("as_of_date"):
            stale_metrics.append({"metric": name, "reason": "missing_as_of_date"})
    return {
        "validation_date": validation_date,
        "stale_metrics": stale_metrics,
        "policy": "flag_missing_dates_do_not_hallucinate_freshness",
    }


def build_valuation_inputs(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "price": metric_value(metrics.get("price_at_analysis")),
        "market_cap": metric_value(metrics.get("market_cap")),
        "pe_ratio": metric_value(metrics.get("pe_ratio")),
        "ev_ebitda": metric_value(metrics.get("ev_ebitda")),
        "fcf_yield": metric_value(metrics.get("fcf_yield")),
        "analyst_target_mean": metric_value(metrics.get("analyst_target_mean")),
    }


def extract_quarterly_rows(*, financial: dict[str, Any], yfinance: dict[str, Any]) -> list[dict[str, Any]]:
    calls = financial.get("calls") if isinstance(financial.get("calls"), dict) else {}
    financial_rows = records_from_payload(calls.get("financials_quarterly"))
    if financial_rows:
        return financial_rows[:8]
    rows = yfinance.get("income_statements") if isinstance(yfinance.get("income_statements"), list) else []
    return [row for row in rows if isinstance(row, dict)][:8]


def infer_currency(*, market: str, yfinance: dict[str, Any], dart: dict[str, Any]) -> str:
    price = yfinance.get("current_price") if isinstance(yfinance.get("current_price"), dict) else {}
    if price.get("currency"):
        return str(price["currency"])
    if dart.get("ttm_income_statement", {}).get("currency"):
        return str(dart["ttm_income_statement"]["currency"])
    return "KRW" if market == "KR" else "USD"


def infer_company_name(
    *,
    dart: dict[str, Any],
    financial: dict[str, Any],
    ticker: str,
    yfinance: dict[str, Any],
) -> str:
    info = yfinance.get("info") if isinstance(yfinance.get("info"), dict) else {}
    return str(
        dart.get("stock_name")
        or dart.get("corp_name")
        or financial.get("company_name")
        or yfinance.get("company_name")
        or info.get("long_name")
        or info.get("short_name")
        or ticker
    )


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def first_dict(rows: list[Any]) -> dict[str, Any]:
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
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
    return round(value * 100, 4) if value is not None else None


def safe_subtract(left: Any, right: Any) -> float | None:
    left_number = as_number(left)
    right_number = as_number(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def billions(value: Any) -> float | None:
    number = as_number(value)
    return round(number / 1_000_000_000, 4) if number is not None else None


def millions(value: Any) -> float | None:
    number = as_number(value)
    return round(number / 1_000_000, 4) if number is not None else None


def sum_recent(rows: list[Any], field: str, limit: int) -> float | None:
    values = [
        as_number(row.get(field))
        for row in rows[:limit]
        if isinstance(row, dict) and as_number(row.get(field)) is not None
    ]
    return sum(value for value in values if value is not None) if values else None


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
                return round(((latest_value - prior_value) / prior_value) * 100, 4)
    return None


def latest_period(rows: list[Any]) -> str | None:
    for row in rows:
        if isinstance(row, dict):
            period = date_part(row.get("period_end"))
            if period:
                return period
    return None


def metric_value(entry: dict[str, Any] | None) -> float | None:
    return as_number(entry.get("value")) if isinstance(entry, dict) else None


def metric_current(entry: Any) -> float | None:
    return as_number(entry.get("value")) if isinstance(entry, dict) else None


def metric_prior(entry: Any) -> float | None:
    return as_number(entry.get("prior")) if isinstance(entry, dict) else None


def dart_year_date(value: Any) -> str | None:
    number = as_number(value)
    if number is None:
        return None
    return f"{int(number):04d}-12-31"


def first_record(payload: Any) -> dict[str, Any]:
    records = records_from_payload(payload)
    return records[0] if records else {}


def latest_record(payload: Any) -> dict[str, Any]:
    records = records_from_payload(payload)
    return records[-1] if records else {}


def records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    financials = payload.get("financials")
    if isinstance(financials, dict):
        for key in ("income_statements", "balance_sheets", "cash_flow_statements"):
            value = financials.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    for key in ("data", "financials", "results", "prices", "filings", "analyst_estimates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload] if payload else []


def pick_number(record: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = as_number(record.get(key))
        if value is not None:
            return value
    return None


def growth_from_quarters(records: list[dict[str, Any]], field: str) -> float | None:
    if len(records) < 5:
        return None
    latest = pick_number(records[0], field)
    prior = pick_number(records[4], field)
    if latest is None or prior in (None, 0):
        return None
    return round(((latest - prior) / prior) * 100, 4)
