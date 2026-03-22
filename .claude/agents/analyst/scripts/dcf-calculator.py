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
    "fcf_growth_rate":     {"type": "float",  "required": True,  "description": "Projected FCF annual growth rate (decimal, e.g., 0.12 = 12%)"},
    "wacc":                {"type": "float",  "required": True,  "description": "Weighted average cost of capital (decimal, e.g., 0.08 = 8%)"},
    "terminal_growth_rate":{"type": "float",  "required": False, "description": "Perpetual growth rate after forecast (decimal), default 0.025", "default": 0.025},
    "forecast_years":      {"type": "int",    "required": False, "description": "Number of explicit forecast years, default 10", "default": 10},
    "net_debt":            {"type": "float",  "required": False, "description": "Net debt (millions USD) = total_debt - cash. Default 0", "default": 0},
    "tax_rate":            {"type": "float",  "required": False, "description": "Effective tax rate (decimal). Not used in FCF-based DCF but logged", "default": None},
    "margin_expansion":    {"type": "float",  "required": False, "description": "Annual margin improvement (decimal, e.g., 0.005 = 0.5%/yr added to growth)", "default": 0},
    "sensitivity_wacc":    {"type": "list",   "required": False, "description": "WACC values for sensitivity table (3 values)", "default": "auto: [wacc-1%, wacc, wacc+1%]"},
    "sensitivity_tgr":     {"type": "list",   "required": False, "description": "Terminal growth rates for sensitivity (3 values)", "default": "auto: [tgr-0.5%, tgr, tgr+0.5%]"},
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


def compute_dcf(fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate, forecast_years, net_debt, diluted_shares, margin_expansion=0):
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

    if fcf_ttm <= 0:
        errors.append(f"WARN: fcf_ttm is {fcf_ttm:.2f} (non-positive). DCF assumes positive FCF for meaningful valuation. Proceeding but result may be negative/misleading.")

    if diluted_shares is None or diluted_shares <= 0:
        return None, ["FAIL: diluted_shares is None or ≤ 0 — cannot compute per-share value"]

    # ── Project explicit-period FCFs ──
    projected_fcfs = []
    effective_growth = fcf_growth_rate + margin_expansion
    current_fcf = fcf_ttm

    for year in range(1, forecast_years + 1):
        current_fcf = current_fcf * (1 + effective_growth)
        projected_fcfs.append(current_fcf)

    formulas["projected_fcf_year1"] = f"{fcf_ttm:.2f}M × (1 + {effective_growth:.4f}) = {projected_fcfs[0]:.2f}M"
    formulas["projected_fcf_yearN"] = f"Year {forecast_years} FCF = {projected_fcfs[-1]:.2f}M"

    # ── Discount explicit-period FCFs ──
    pv_explicit = 0
    for year, fcf in enumerate(projected_fcfs, start=1):
        pv_explicit += fcf / ((1 + wacc) ** year)

    pv_explicit = round(pv_explicit, 2)
    formulas["pv_explicit_fcf"] = f"Sum of {forecast_years} discounted FCFs = {pv_explicit:.2f}M"

    # ── Terminal Value ──
    terminal_fcf = projected_fcfs[-1] * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
    pv_terminal = terminal_value / ((1 + wacc) ** forecast_years)
    pv_terminal = round(pv_terminal, 2)

    formulas["terminal_value"] = f"{terminal_fcf:.2f}M / ({wacc:.4f} - {terminal_growth_rate:.4f}) = {terminal_value:.2f}M"
    formulas["pv_terminal_value"] = f"{terminal_value:.2f}M / (1 + {wacc:.4f})^{forecast_years} = {pv_terminal:.2f}M"

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

    return {
        "pv_explicit_fcf": pv_explicit,
        "pv_terminal_value": pv_terminal,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "fair_value_per_share": fair_value_per_share,
        "formulas": formulas,
    }, errors


def build_sensitivity_table(fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate,
                            forecast_years, net_debt, diluted_shares, margin_expansion,
                            wacc_values, tgr_values, current_price):
    """Build 3×3 sensitivity table: WACC rows × terminal growth rate columns."""
    table = []
    for w in wacc_values:
        row = {"wacc": f"{w*100:.1f}%"}
        for tg in tgr_values:
            if w <= tg:
                row[f"tgr_{tg*100:.1f}%"] = None  # invalid combination
            else:
                result, _ = compute_dcf(fcf_ttm, fcf_growth_rate, w, tg,
                                        forecast_years, net_debt, diluted_shares, margin_expansion)
                if result and result["fair_value_per_share"] is not None:
                    fv = result["fair_value_per_share"]
                    upside = round((fv - current_price) / current_price * 100, 1) if current_price else None
                    row[f"tgr_{tg*100:.1f}%"] = {"fair_value": fv, "upside_pct": upside}
                else:
                    row[f"tgr_{tg*100:.1f}%"] = None
        table.append(row)
    return table


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
    wacc = inputs.get("wacc")
    terminal_growth_rate = inputs.get("terminal_growth_rate", 0.025)
    forecast_years = inputs.get("forecast_years", 10)
    net_debt = inputs.get("net_debt", 0)
    tax_rate = inputs.get("tax_rate")
    margin_expansion = inputs.get("margin_expansion", 0)

    # Log assumptions for transparency
    assumptions = {
        "scenario": scenario_name,
        "fcf_ttm": fcf_ttm,
        "fcf_growth_rate": fcf_growth_rate,
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth_rate,
        "forecast_years": forecast_years,
        "net_debt": net_debt,
        "margin_expansion": margin_expansion,
        "tax_rate": tax_rate,
    }

    # ── Core DCF ──
    result, dcf_errors = compute_dcf(
        fcf_ttm, fcf_growth_rate, wacc, terminal_growth_rate,
        forecast_years, net_debt, diluted_shares, margin_expansion
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
            wacc_values, tgr_values, current_price
        )

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
