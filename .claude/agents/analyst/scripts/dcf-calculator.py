#!/usr/bin/env python3
"""
dcf-calculator.py — Scenario-based DCF intrinsic value calculator.

Usage:
    python dcf-calculator.py --input <json_file>
    python dcf-calculator.py --inline '{"fcf_ttm": 95000, "fcf_growth_rate": 0.12, ...}'
    python dcf-calculator.py --schema

Follows the same interface pattern as ratio-calculator.py:
  - All inputs optional (missing → null output, not crash)
  - safe_divide() for zero/NaN protection
  - Blank-Over-Wrong: invalid inputs (e.g., WACC ≤ terminal_growth) → null + warning
  - --schema flag for self-documenting interface

Output includes:
  - Per-scenario DCF fair value
  - Base case 9-cell sensitivity table (WACC × terminal growth)
  - Bull/Bear single-point DCF values
  - All formulas shown for auditability
"""

import sys
import json
import argparse
import math

# ── Schema (single source of truth) ─────────────────────────────────────

INPUT_SCHEMA = {
    "scenario_name":       {"type": "string", "required": False, "description": "Scenario label: bull / base / bear", "default": "base"},
    "current_price":       {"type": "float",  "required": True,  "description": "Current stock price (USD)"},
    "diluted_shares":      {"type": "float",  "required": True,  "description": "Diluted shares outstanding (millions)"},
    "fcf_ttm":             {"type": "float",  "required": True,  "description": "TTM free cash flow (millions USD)"},
    "fcf_growth_rate":     {"type": "float",  "required": False, "description": "Projected FCF annual growth rate (decimal, e.g., 0.12 = 12%). Optional when growth_rates is supplied."},
    "growth_rates":        {"type": "list",   "required": False, "description": "Explicit per-year FCF growth path. Must contain at least forecast_years values.", "default": None},
    "mid_year_convention": {"type": "boolean", "required": False, "description": "If true, discount projected FCFs at 0.5, 1.5, 2.5... periods. Default off.", "default": False},
    "wacc":                {"type": "float",  "required": False, "description": "Weighted average cost of capital (decimal, e.g., 0.08 = 8%). If omitted, auto-calculated from component inputs.", "default": None},
    "risk_free_rate":      {"type": "float",  "required": False, "description": "Risk-free rate from FRED DGS10 (decimal, e.g., 0.0425 = 4.25%)", "default": None},
    "beta":                {"type": "float",  "required": False, "description": "Equity beta from financial metrics", "default": None},
    "erp":                 {"type": "float",  "required": False, "description": "Equity risk premium (decimal, e.g., 0.055 = 5.5%)", "default": None},
    "debt_to_value":       {"type": "float",  "required": False, "description": "D/V ratio (decimal, e.g., 0.3 = 30%)", "default": None},
    "cost_of_debt":        {"type": "float",  "required": False, "description": "Pre-tax cost of debt (decimal, e.g., 0.05 = 5%)", "default": None},
    "terminal_growth_rate":{"type": "float",  "required": False, "description": "Perpetual growth rate after forecast (decimal), default 0.025", "default": 0.025},
    "forecast_years":      {"type": "int",    "required": False, "description": "Number of explicit forecast years, default 10", "default": 10},
    "net_debt":            {"type": "float",  "required": False, "description": "Net debt (millions USD) = total_debt - cash. Default 0", "default": 0},
    "tax_rate":            {"type": "float",  "required": False, "description": "Effective tax rate (decimal). Used in WACC calculation if debt components provided.", "default": None},
    "margin_expansion":    {"type": "float",  "required": False, "description": "Annual margin improvement (decimal, e.g., 0.005 = 0.5%/yr added to growth)", "default": 0},
    "sensitivity_wacc":    {"type": "list",   "required": False, "description": "WACC values for sensitivity table (3 values)", "default": "auto: [wacc-1%, wacc, wacc+1%]"},
    "sensitivity_tgr":     {"type": "list",   "required": False, "description": "Terminal growth rates for sensitivity (3 values)", "default": "auto: [tgr-0.5%, tgr, tgr+0.5%]"},
    "current_price_for_reverse": {"type": "float", "required": False, "description": "If provided, additionally solve for the FCF growth rate that the market implicitly prices into this stock price (Reverse DCF / Expectations Investing).", "default": None},
    "peer_median_ev_ebitda": {"type": "float", "required": False, "description": "Peer median EV/EBITDA multiple for trading-comp reconciliation.", "default": None},
    "target_ttm_ebitda": {"type": "float", "required": False, "description": "Target company's TTM EBITDA (millions) for trading-comp reconciliation.", "default": None},
    "weight_dcf": {"type": "float", "required": False, "description": "DCF weight in valuation reconciliation.", "default": 0.6},
    "weight_comps": {"type": "float", "required": False, "description": "Trading comps weight in valuation reconciliation.", "default": 0.4},
    "capex_growth_rate": {"type": "float", "required": False, "description": "Optional capex growth/reinvestment assumption for pitfall checks.", "default": None},
}

OUTPUT_SCHEMA = {
    "scenario":             "string — scenario label",
    "pv_explicit_fcf":      "float or null — PV of forecast-period FCFs (millions)",
    "pv_terminal_value":    "float or null — PV of terminal value (millions)",
    "enterprise_value":     "float or null — pv_explicit_fcf + pv_terminal_value (millions)",
    "equity_value":         "float or null — enterprise_value - net_debt (millions)",
    "fair_value_per_share": "float or null — equity_value / diluted_shares",
    "upside_downside_pct":  "float or null — (fair_value - current_price) / current_price × 100",
    "sensitivity_table":    "list of dicts — 3×3 grid: WACC rows × terminal growth columns",
    "assumptions":          "dict — all assumptions used, for transparency",
    "formulas":             "dict — human-readable formula strings",
    "wacc_derivation":      "dict or null — how WACC was determined (method, components, calculated value)",
    "reverse_dcf":          "dict or null — implied FCF growth result when current_price_for_reverse is provided",
    "valuation_reconciliation": "dict — DCF vs trading-comp implied value, when inputs are available",
    "errors":               "list — warnings and errors",
}


# ── Helpers ──────────────────────────────────────────────────────────────

def safe_divide(numerator, denominator, error_msg=None):
    """Return numerator/denominator or None if denominator is zero/None/NaN."""
    if denominator is None or denominator == 0:
        return None, error_msg or "Division by zero or missing denominator"
    if numerator is None:
        return None, error_msg or "Numerator is None"
    try:
        if math.isnan(denominator) or math.isnan(numerator):
            return None, error_msg or "NaN in inputs"
    except TypeError:
        pass
    return numerator / denominator, None


def compute_dcf(
    fcf_ttm,
    fcf_growth_rate,
    wacc,
    terminal_growth_rate,
    forecast_years,
    net_debt,
    diluted_shares,
    margin_expansion=0,
    growth_rates=None,
    mid_year_convention=False,
):
    """
    Core DCF computation.

    FCF projection:
      Year 1 FCF = fcf_ttm × (1 + fcf_growth_rate + margin_expansion)
      Year N FCF = Year(N-1) × (1 + growth_rate + margin_expansion)

    Terminal Value:
      TV = Year_N_FCF × (1 + terminal_growth_rate) / (WACC - terminal_growth_rate)

    Returns (results_dict, errors_list) or (None, errors_list) on invalid inputs.
    """
    errors = []
    formulas = {}

    # ── Validate: Blank-Over-Wrong ──
    if wacc is None or terminal_growth_rate is None:
        return None, ["FAIL: WACC or terminal_growth_rate is None — cannot compute DCF"]

    if wacc <= terminal_growth_rate:
        return None, [f"FAIL: WACC ({wacc:.4f}) ≤ terminal_growth_rate ({terminal_growth_rate:.4f}) — DCF mathematically invalid. Returning null (Blank-Over-Wrong principle)."]

    if fcf_ttm is None:
        return None, ["FAIL: fcf_ttm is None — cannot project future cash flows"]
    if growth_rates is None and fcf_growth_rate is None:
        return None, ["FAIL: fcf_growth_rate is None and growth_rates not supplied — cannot project future cash flows"]
    if growth_rates is not None:
        if not isinstance(growth_rates, list) or len(growth_rates) < forecast_years:
            return None, [f"FAIL: growth_rates must contain at least forecast_years ({forecast_years}) values"]
        if not all(isinstance(rate, (int, float)) and not isinstance(rate, bool) for rate in growth_rates[:forecast_years]):
            return None, ["FAIL: growth_rates must contain only numeric decimal growth rates"]

    if fcf_ttm <= 0:
        errors.append(f"WARN: fcf_ttm is {fcf_ttm:.2f} (non-positive). DCF assumes positive FCF for meaningful valuation. Proceeding but result may be negative/misleading.")

    if diluted_shares is None or diluted_shares <= 0:
        return None, ["FAIL: diluted_shares is None or ≤ 0 — cannot compute per-share value"]

    # ── Project explicit-period FCFs ──
    projected_fcfs = []
    effective_growth = (fcf_growth_rate or 0) + margin_expansion
    current_fcf = fcf_ttm

    growth_path = []
    for year_index in range(forecast_years):
        growth = growth_rates[year_index] if growth_rates is not None else effective_growth
        growth_path.append(growth)
        current_fcf = current_fcf * (1 + growth)
        projected_fcfs.append(current_fcf)

    formulas["projected_fcf_year1"] = f"{fcf_ttm:.2f}M × (1 + {growth_path[0]:.4f}) = {projected_fcfs[0]:.2f}M"
    formulas["projected_fcf_yearN"] = f"Year {forecast_years} FCF = {projected_fcfs[-1]:.2f}M"
    if growth_rates is not None:
        formulas["growth_path"] = "Explicit per-year growth rates: " + ", ".join(f"{rate:.2%}" for rate in growth_path)

    # ── Discount explicit-period FCFs ──
    pv_explicit = 0
    for year_index, fcf in enumerate(projected_fcfs):
        discount_period = year_index + 0.5 if mid_year_convention else year_index + 1
        pv_explicit += fcf / ((1 + wacc) ** discount_period)

    pv_explicit = round(pv_explicit, 2)
    timing_note = "mid-year convention" if mid_year_convention else "end-of-year convention"
    formulas["pv_explicit_fcf"] = f"Sum of {forecast_years} discounted FCFs ({timing_note}) = {pv_explicit:.2f}M"

    # ── Terminal Value ──
    terminal_fcf = projected_fcfs[-1] * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
    terminal_discount_period = forecast_years - 0.5 if mid_year_convention else forecast_years
    pv_terminal = terminal_value / ((1 + wacc) ** terminal_discount_period)
    pv_terminal = round(pv_terminal, 2)

    formulas["terminal_value"] = f"{terminal_fcf:.2f}M / ({wacc:.4f} - {terminal_growth_rate:.4f}) = {terminal_value:.2f}M"
    formulas["pv_terminal_value"] = f"{terminal_value:.2f}M / (1 + {wacc:.4f})^{terminal_discount_period:.1f} = {pv_terminal:.2f}M"

    # ── Enterprise Value → Equity Value → Per Share ──
    enterprise_value = round(pv_explicit + pv_terminal, 2)
    equity_value = round(enterprise_value - (net_debt or 0), 2)

    fair_value_per_share, err = safe_divide(equity_value, diluted_shares)
    if err:
        errors.append(f"WARN: {err}")
        fair_value_per_share = None
    else:
        fair_value_per_share = round(fair_value_per_share, 2)

    formulas["enterprise_value"] = f"{pv_explicit:.2f}M + {pv_terminal:.2f}M = {enterprise_value:.2f}M"
    formulas["equity_value"] = f"{enterprise_value:.2f}M - {net_debt or 0:.2f}M net_debt = {equity_value:.2f}M"
    if fair_value_per_share is not None:
        formulas["fair_value_per_share"] = f"{equity_value:.2f}M / {diluted_shares:.2f}M shares = ${fair_value_per_share:.2f}"

    if pv_terminal and enterprise_value and enterprise_value > 0:
        terminal_ratio = pv_terminal / enterprise_value
        if terminal_ratio > 0.75:
            errors.append(
                f"Terminal value is {terminal_ratio:.1%} of EV — model may be over-reliant on terminal assumptions (target: 40-75%)."
            )
        elif terminal_ratio < 0.40:
            errors.append(
                f"Terminal value is only {terminal_ratio:.1%} of EV — terminal assumptions may be too conservative or forecast period too long."
            )

    return {
        "pv_explicit_fcf": pv_explicit,
        "pv_terminal_value": pv_terminal,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "fair_value_per_share": fair_value_per_share,
        "formulas": formulas,
    }, errors


def solve_implied_growth(
    target_price,
    fcf_ttm,
    wacc,
    terminal_growth_rate,
    forecast_years,
    net_debt,
    diluted_shares,
    *,
    growth_floor_offset=0.001,
    growth_ceiling=1.0,
    tolerance=0.0005,
    max_iterations=50,
):
    """Solve for the FCF growth rate the market implies at target_price.

    Bisection over `compute_dcf` since fair_value is monotonically increasing
    in growth (everything else held constant).
    """
    base = {
        "target_price": target_price,
        "implied_fcf_growth": None,
        "iterations": 0,
        "bracket_low": None,
        "bracket_high": None,
        "fair_value_at_floor": None,
        "fair_value_at_ceiling": None,
    }

    if wacc is None or terminal_growth_rate is None or wacc <= terminal_growth_rate:
        return {**base, "status": "wacc_invalid",
                "notes": "WACC must exceed terminal growth."}
    if fcf_ttm is None or fcf_ttm <= 0:
        return {**base, "status": "negative_fcf",
                "notes": "Reverse DCF requires positive FCF TTM."}
    if target_price is None or target_price <= 0 or diluted_shares is None or diluted_shares <= 0:
        return {**base, "status": "invalid_input",
                "notes": "Target price and diluted shares must be positive."}

    def fair_at(growth):
        result, _errors = compute_dcf(
            fcf_ttm=fcf_ttm,
            fcf_growth_rate=growth,
            wacc=wacc,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
            net_debt=net_debt,
            diluted_shares=diluted_shares,
            margin_expansion=0,
        )
        if result is None:
            return None
        return result.get("fair_value_per_share")

    low = terminal_growth_rate + growth_floor_offset
    high = growth_ceiling
    fair_low = fair_at(low)
    fair_high = fair_at(high)
    base.update({
        "bracket_low": low,
        "bracket_high": high,
        "fair_value_at_floor": fair_low,
        "fair_value_at_ceiling": fair_high,
    })

    if fair_low is None or fair_high is None:
        return {**base, "status": "did_not_converge",
                "notes": "DCF failed at bracket bounds."}
    if target_price > fair_high:
        return {**base, "status": "exceeds_ceiling",
                "notes": "Target price requires growth above ceiling."}
    if target_price < fair_low:
        return {**base, "status": "below_floor",
                "notes": "Target price is below floor-growth DCF value."}

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        mid = (low + high) / 2
        fair_mid = fair_at(mid)
        if fair_mid is None:
            return {**base, "status": "did_not_converge",
                    "iterations": iterations,
                    "notes": "DCF failed mid-bisection."}
        if fair_mid < target_price:
            low = mid
        else:
            high = mid
        if (high - low) < tolerance:
            implied = round((low + high) / 2, 4)
            return {**base, "status": "success",
                    "implied_fcf_growth": implied,
                    "iterations": iterations,
                    "notes": f"Converged in {iterations} iterations."}

    return {**base, "status": "did_not_converge",
            "iterations": iterations,
            "notes": f"Bisection did not converge in {max_iterations} iterations."}


def build_sensitivity_table(fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate,
                            forecast_years, net_debt, diluted_shares, margin_expansion,
                            wacc_values, tgr_values, current_price, growth_rates=None,
                            mid_year_convention=False):
    """Build 3×3 sensitivity table: WACC rows × terminal growth rate columns."""
    table = []
    for w in wacc_values:
        row = {"wacc": f"{w*100:.1f}%"}
        for tg in tgr_values:
            if w <= tg:
                row[f"tgr_{tg*100:.1f}%"] = None  # invalid combination
            else:
                result, _ = compute_dcf(
                    fcf_ttm, fcf_growth_rate, w, tg,
                    forecast_years, net_debt, diluted_shares, margin_expansion,
                    growth_rates=growth_rates,
                    mid_year_convention=mid_year_convention,
                )
                if result and result["fair_value_per_share"] is not None:
                    fv = result["fair_value_per_share"]
                    upside = round((fv - current_price) / current_price * 100, 1) if current_price else None
                    row[f"tgr_{tg*100:.1f}%"] = {"fair_value": fv, "upside_pct": upside}
                else:
                    row[f"tgr_{tg*100:.1f}%"] = None
        table.append(row)
    return table


def reconcile_with_comps(
    dcf_fair_value_per_share,
    peer_median_ev_ebitda,
    target_ttm_ebitda,
    diluted_shares,
    net_debt,
    weight_dcf=0.6,
    weight_comps=0.4,
):
    """Combine DCF fair value with trading-comp implied value."""
    if peer_median_ev_ebitda is None or target_ttm_ebitda is None or target_ttm_ebitda <= 0:
        return {
            "dcf_fair_value_per_share": dcf_fair_value_per_share,
            "comp_implied_per_share": None,
            "weighted_fair_value": dcf_fair_value_per_share,
            "weights": {"dcf": 1.0, "comps": 0.0},
            "method": "dcf_only",
            "reason": "peer comp inputs missing",
        }

    comp_ev = peer_median_ev_ebitda * target_ttm_ebitda
    comp_equity = comp_ev - (net_debt or 0)
    comp_per_share, _ = safe_divide(comp_equity, diluted_shares)
    if comp_per_share is not None:
        comp_per_share = round(comp_per_share, 2)

    if dcf_fair_value_per_share is None or comp_per_share is None:
        return {
            "dcf_fair_value_per_share": dcf_fair_value_per_share,
            "comp_implied_per_share": comp_per_share,
            "weighted_fair_value": dcf_fair_value_per_share or comp_per_share,
            "weights": {
                "dcf": 1.0 if dcf_fair_value_per_share else 0.0,
                "comps": 1.0 if comp_per_share else 0.0,
            },
            "method": "single_method",
        }

    total_weight = weight_dcf + weight_comps
    if total_weight <= 0:
        weight_dcf, weight_comps = 0.6, 0.4
        total_weight = 1.0
    normalized_dcf = weight_dcf / total_weight
    normalized_comps = weight_comps / total_weight
    weighted = normalized_dcf * dcf_fair_value_per_share + normalized_comps * comp_per_share
    return {
        "dcf_fair_value_per_share": dcf_fair_value_per_share,
        "comp_implied_per_share": comp_per_share,
        "weighted_fair_value": round(weighted, 2),
        "weights": {"dcf": round(normalized_dcf, 4), "comps": round(normalized_comps, 4)},
        "method": "weighted_dcf_comps",
        "premium_or_discount_pct": round((comp_per_share - dcf_fair_value_per_share) / dcf_fair_value_per_share * 100, 2)
        if dcf_fair_value_per_share
        else None,
    }


def pitfall_warnings(inputs, *, fcf_growth_rate, growth_rates, terminal_growth_rate, mid_year_convention):
    warnings = []
    growth_path = growth_rates if isinstance(growth_rates, list) and growth_rates else [fcf_growth_rate]
    max_growth = max((rate for rate in growth_path if isinstance(rate, (int, float)) and not isinstance(rate, bool)), default=None)
    if max_growth is not None and max_growth > 0.15 and inputs.get("capex_growth_rate") is None:
        warnings.append(
            "WARN: FCF growth above 15% without explicit capex/reinvestment assumption — check double-counting growth without reinvestment."
        )
    if terminal_growth_rate is not None and terminal_growth_rate > 0.04:
        warnings.append(
            "WARN: terminal_growth_rate exceeds 4% — verify against plausible long-run GDP growth."
        )
    if mid_year_convention and growth_rates:
        warnings.append(
            "INFO: mid_year_convention applied uniformly to the explicit per-year FCF growth path."
        )
    return warnings


# ── Main ─────────────────────────────────────────────────────────────────

def calculate_dcf(inputs: dict) -> dict:
    """Main entry point. Takes input dict, returns full DCF result."""
    errors = []

    # Extract with defaults
    scenario_name = inputs.get("scenario_name", "base")
    current_price = inputs.get("current_price")
    diluted_shares = inputs.get("diluted_shares")
    fcf_ttm = inputs.get("fcf_ttm")
    fcf_growth_rate = inputs.get("fcf_growth_rate")
    growth_rates = inputs.get("growth_rates")
    mid_year_convention = bool(inputs.get("mid_year_convention", False))
    wacc = inputs.get("wacc")
    risk_free_rate = inputs.get("risk_free_rate")
    beta = inputs.get("beta")
    erp = inputs.get("erp")
    debt_to_value = inputs.get("debt_to_value")
    cost_of_debt = inputs.get("cost_of_debt")
    terminal_growth_rate = inputs.get("terminal_growth_rate", 0.025)
    forecast_years = inputs.get("forecast_years", 10)
    net_debt = inputs.get("net_debt", 0)
    tax_rate = inputs.get("tax_rate")
    margin_expansion = inputs.get("margin_expansion", 0)

    # ── WACC Resolution ──
    # Priority: explicit wacc > component-based > error
    wacc_derivation = None

    if wacc is not None:
        wacc_derivation = {"method": "manual", "wacc": wacc}
    elif risk_free_rate is not None and beta is not None and erp is not None:
        cost_of_equity = risk_free_rate + beta * erp
        if debt_to_value is not None and cost_of_debt is not None and tax_rate is not None:
            equity_to_value = 1.0 - debt_to_value
            wacc = (equity_to_value * cost_of_equity) + (debt_to_value * cost_of_debt * (1 - tax_rate))
            wacc_derivation = {
                "method": "FRED-based",
                "risk_free_rate": risk_free_rate,
                "risk_free_source": "FRED DGS10",
                "beta": beta, "erp": erp,
                "cost_of_equity": round(cost_of_equity, 5),
                "debt_to_value": debt_to_value,
                "cost_of_debt": cost_of_debt,
                "tax_rate": tax_rate,
                "calculated_wacc": round(wacc, 5),
            }
        else:
            wacc = cost_of_equity
            wacc_derivation = {
                "method": "FRED-based (equity-only)",
                "risk_free_rate": risk_free_rate,
                "risk_free_source": "FRED DGS10",
                "beta": beta, "erp": erp,
                "cost_of_equity": round(cost_of_equity, 5),
                "calculated_wacc": round(wacc, 5),
                "note": "Debt components not provided — Cost of Equity used as WACC",
            }
        errors.append(f"INFO: WACC auto-calculated from FRED components: {wacc:.4f}")

    # Log assumptions for transparency
    assumptions = {
        "scenario": scenario_name,
        "fcf_ttm": fcf_ttm,
        "fcf_growth_rate": fcf_growth_rate,
        "growth_rates": growth_rates,
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth_rate,
        "forecast_years": forecast_years,
        "net_debt": net_debt,
        "margin_expansion": margin_expansion,
        "mid_year_convention": mid_year_convention,
        "tax_rate": tax_rate,
    }

    errors.extend(
        pitfall_warnings(
            inputs,
            fcf_growth_rate=fcf_growth_rate,
            growth_rates=growth_rates,
            terminal_growth_rate=terminal_growth_rate,
            mid_year_convention=mid_year_convention,
        )
    )

    # ── Core DCF ──
    result, dcf_errors = compute_dcf(
        fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate,
        forecast_years, net_debt, diluted_shares, margin_expansion,
        growth_rates=growth_rates,
        mid_year_convention=mid_year_convention,
    )
    errors.extend(dcf_errors)

    if result is None:
        return {
            "scenario": scenario_name,
            "pv_explicit_fcf": None,
            "pv_terminal_value": None,
            "enterprise_value": None,
            "equity_value": None,
            "fair_value_per_share": None,
            "upside_downside_pct": None,
            "sensitivity_table": None,
            "assumptions": assumptions,
            "formulas": {},
            "wacc_derivation": wacc_derivation,
            "reverse_dcf": None,
            "valuation_reconciliation": reconcile_with_comps(
                None,
                inputs.get("peer_median_ev_ebitda"),
                inputs.get("target_ttm_ebitda"),
                diluted_shares,
                net_debt,
                inputs.get("weight_dcf", 0.6),
                inputs.get("weight_comps", 0.4),
            ),
            "errors": errors,
        }

    # ── Upside/Downside ──
    upside = None
    if result["fair_value_per_share"] is not None and current_price is not None and current_price > 0:
        upside = round((result["fair_value_per_share"] - current_price) / current_price * 100, 2)
        result["formulas"]["upside_downside_pct"] = (
            f"({result['fair_value_per_share']:.2f} - {current_price:.2f}) / {current_price:.2f} × 100 = {upside:.2f}%"
        )

    # ── Sensitivity Table (Base case only, per eng review decision #7) ──
    sensitivity_table = None
    if scenario_name == "base" and wacc is not None and terminal_growth_rate is not None:
        wacc_values = inputs.get("sensitivity_wacc") or [wacc - 0.01, wacc, wacc + 0.01]
        tgr_values = inputs.get("sensitivity_tgr") or [terminal_growth_rate - 0.005, terminal_growth_rate, terminal_growth_rate + 0.005]

        # Ensure no negative rates
        wacc_values = [max(0.01, w) for w in wacc_values]
        tgr_values = [max(0.0, t) for t in tgr_values]

        sensitivity_table = build_sensitivity_table(
            fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate,
            forecast_years, net_debt, diluted_shares, margin_expansion,
            wacc_values, tgr_values, current_price,
            growth_rates=growth_rates,
            mid_year_convention=mid_year_convention,
        )

    # ── Reverse DCF (Expectations Investing) ──
    # Solve for the FCF growth rate the market implies at current_price_for_reverse.
    reverse_dcf = None
    current_price_for_reverse = inputs.get("current_price_for_reverse")
    if current_price_for_reverse is not None:
        implied = solve_implied_growth(
            target_price=current_price_for_reverse,
            fcf_ttm=fcf_ttm,
            wacc=wacc,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
            net_debt=net_debt,
            diluted_shares=diluted_shares,
        )
        if implied.get("status") == "success" and fcf_growth_rate is not None:
            implied["analyst_growth_assumption"] = fcf_growth_rate
            implied["growth_gap_bp"] = round(
                (implied["implied_fcf_growth"] - fcf_growth_rate) * 10000,
                1,
            )
        reverse_dcf = implied

    return {
        "scenario": scenario_name,
        "pv_explicit_fcf": result["pv_explicit_fcf"],
        "pv_terminal_value": result["pv_terminal_value"],
        "enterprise_value": result["enterprise_value"],
        "equity_value": result["equity_value"],
        "fair_value_per_share": result["fair_value_per_share"],
        "upside_downside_pct": upside,
        "sensitivity_table": sensitivity_table,
        "assumptions": assumptions,
        "formulas": result["formulas"],
        "wacc_derivation": wacc_derivation,
        "reverse_dcf": reverse_dcf,
        "valuation_reconciliation": reconcile_with_comps(
            result["fair_value_per_share"],
            inputs.get("peer_median_ev_ebitda"),
            inputs.get("target_ttm_ebitda"),
            diluted_shares,
            net_debt,
            inputs.get("weight_dcf", 0.6),
            inputs.get("weight_comps", 0.4),
        ),
        "errors": errors,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Scenario-based DCF intrinsic value calculator")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--input", help="Path to input JSON file")
    group.add_argument("--inline", help="Inline JSON string")
    parser.add_argument("--schema", action="store_true", help="Print input/output JSON schema and exit")
    args = parser.parse_args()

    if args.schema:
        schema = {"input_fields": INPUT_SCHEMA, "output_fields": OUTPUT_SCHEMA}
        print(json.dumps(schema, ensure_ascii=False, indent=2))
        return

    if not args.input and not args.inline:
        parser.error("one of the arguments --input --inline --schema is required")

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            inputs = json.load(f)
    else:
        inputs = json.loads(args.inline)

    result = calculate_dcf(inputs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
