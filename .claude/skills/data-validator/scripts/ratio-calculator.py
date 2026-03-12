#!/usr/bin/env python3
"""
ratio-calculator.py — Deterministic financial ratio calculator.

Usage:
    python ratio-calculator.py --input <json_file>
    python ratio-calculator.py --inline '{"price": 175.50, "diluted_shares": 15500, ...}'

Input JSON fields (all optional but more = more ratios computed):
    price               : float  — current stock price (USD or KRW)
    diluted_shares      : float  — diluted shares outstanding (millions)
    net_income_ttm      : float  — TTM net income (millions)
    ebitda_ttm          : float  — TTM EBITDA (millions)
    total_debt          : float  — total debt = short-term + long-term (millions)
    cash                : float  — cash and equivalents (millions)
    operating_cf        : float  — TTM operating cash flow (millions)
    capex               : float  — TTM capital expenditure, use positive number (millions)
    revenue_ttm         : float  — TTM revenue (millions)
    operating_income_ttm: float  — TTM operating income (millions)
    gross_profit_ttm    : float  — TTM gross profit (millions)
    enterprise_value    : float  — override EV if pre-computed (millions); if omitted, calculated

Output JSON:
    market_cap          : float  — price × diluted_shares (millions)
    net_debt            : float  — total_debt - cash (millions)
    enterprise_value    : float  — market_cap + net_debt (millions)
    eps_ttm             : float  — net_income_ttm / diluted_shares
    pe_ratio            : float or null
    ev_ebitda           : float or null
    fcf_ttm             : float  — operating_cf - capex (millions)
    fcf_yield           : float  — (fcf_ttm / market_cap) × 100 (%)
    gross_margin        : float  — gross_profit_ttm / revenue_ttm × 100 (%)
    operating_margin    : float  — operating_income_ttm / revenue_ttm × 100 (%)
    net_margin          : float  — net_income_ttm / revenue_ttm × 100 (%)
    net_debt_ebitda     : float or null
    formulas            : dict   — human-readable formula string for each computed ratio
    errors              : list   — list of error/warning messages
    inputs_used         : dict   — echo of inputs used in calculation
"""

import sys
import json
import argparse
import math

def safe_divide(numerator, denominator, error_msg=None):
    """Return numerator/denominator or None if denominator is zero/None."""
    if denominator is None or denominator == 0 or math.isnan(denominator):
        return None, error_msg or f"Division by zero or missing denominator"
    if numerator is None or math.isnan(numerator):
        return None, error_msg or f"Numerator is None or NaN"
    return numerator / denominator, None


def calculate_ratios(inputs: dict) -> dict:
    errors = []
    formulas = {}
    results = {}

    # --- Extract inputs (default None if missing) ---
    price = inputs.get("price")
    diluted_shares = inputs.get("diluted_shares")  # in millions
    net_income_ttm = inputs.get("net_income_ttm")  # in millions
    ebitda_ttm = inputs.get("ebitda_ttm")           # in millions
    total_debt = inputs.get("total_debt", 0)         # in millions
    cash = inputs.get("cash", 0)                     # in millions
    operating_cf = inputs.get("operating_cf")        # in millions
    capex = inputs.get("capex", 0)                   # in millions (positive)
    revenue_ttm = inputs.get("revenue_ttm")          # in millions
    operating_income_ttm = inputs.get("operating_income_ttm")  # in millions
    gross_profit_ttm = inputs.get("gross_profit_ttm")          # in millions
    ev_override = inputs.get("enterprise_value")     # optional override

    # --- Market Cap ---
    if price is not None and diluted_shares is not None:
        market_cap = price * diluted_shares
        results["market_cap"] = round(market_cap, 2)
        formulas["market_cap"] = f"{price} × {diluted_shares}M shares = {market_cap:.2f}M"
    else:
        market_cap = None
        results["market_cap"] = None
        if price is None:
            errors.append("WARN: price not provided — market_cap, P/E, FCF Yield cannot be computed")
        if diluted_shares is None:
            errors.append("WARN: diluted_shares not provided — market_cap, EPS cannot be computed")

    # --- Net Debt ---
    net_debt = (total_debt or 0) - (cash or 0)
    results["net_debt"] = round(net_debt, 2)
    formulas["net_debt"] = f"{total_debt}M debt - {cash}M cash = {net_debt:.2f}M"

    # --- Enterprise Value ---
    if ev_override is not None:
        enterprise_value = ev_override
        results["enterprise_value"] = round(enterprise_value, 2)
        formulas["enterprise_value"] = f"Override provided: {ev_override}M"
    elif market_cap is not None:
        enterprise_value = market_cap + net_debt
        results["enterprise_value"] = round(enterprise_value, 2)
        formulas["enterprise_value"] = f"{market_cap:.2f}M mkt_cap + {net_debt:.2f}M net_debt = {enterprise_value:.2f}M"
    else:
        enterprise_value = None
        results["enterprise_value"] = None
        errors.append("WARN: enterprise_value cannot be computed — market_cap unavailable")

    # --- EPS (diluted) ---
    if net_income_ttm is not None and diluted_shares is not None and diluted_shares > 0:
        eps = net_income_ttm / diluted_shares
        results["eps_ttm"] = round(eps, 4)
        formulas["eps_ttm"] = f"{net_income_ttm}M / {diluted_shares}M shares = {eps:.4f}"
    else:
        results["eps_ttm"] = None
        if net_income_ttm is None:
            errors.append("WARN: net_income_ttm not provided — EPS cannot be computed")

    # --- P/E Ratio ---
    if net_income_ttm is not None and net_income_ttm <= 0:
        results["pe_ratio"] = None
        errors.append("INFO: net_income_ttm <= 0 — P/E ratio not meaningful (company not profitable on TTM basis)")
        formulas["pe_ratio"] = "Not applicable (TTM net income <= 0)"
    elif price is not None and results.get("eps_ttm") is not None and results["eps_ttm"] != 0:
        pe = price / results["eps_ttm"]
        results["pe_ratio"] = round(pe, 2)
        formulas["pe_ratio"] = f"{price} / {results['eps_ttm']:.4f} EPS = {pe:.2f}x"
    else:
        results["pe_ratio"] = None
        if results.get("eps_ttm") is None:
            errors.append("WARN: pe_ratio cannot be computed — EPS unavailable")

    # --- EV/EBITDA ---
    if ebitda_ttm is not None and ebitda_ttm <= 0:
        results["ev_ebitda"] = None
        errors.append("INFO: ebitda_ttm <= 0 — EV/EBITDA not meaningful")
        formulas["ev_ebitda"] = "Not applicable (EBITDA <= 0)"
    elif enterprise_value is not None and ebitda_ttm is not None and ebitda_ttm > 0:
        ev_ebitda = enterprise_value / ebitda_ttm
        results["ev_ebitda"] = round(ev_ebitda, 2)
        formulas["ev_ebitda"] = f"{enterprise_value:.2f}M EV / {ebitda_ttm}M EBITDA = {ev_ebitda:.2f}x"
    else:
        results["ev_ebitda"] = None
        if ebitda_ttm is None:
            errors.append("WARN: ebitda_ttm not provided — EV/EBITDA cannot be computed")
        elif enterprise_value is None:
            errors.append("WARN: EV unavailable — EV/EBITDA cannot be computed")

    # --- FCF ---
    if operating_cf is not None:
        fcf = operating_cf - (capex or 0)
        results["fcf_ttm"] = round(fcf, 2)
        formulas["fcf_ttm"] = f"{operating_cf}M op_cf - {capex}M capex = {fcf:.2f}M"
    else:
        fcf = None
        results["fcf_ttm"] = None
        errors.append("WARN: operating_cf not provided — FCF cannot be computed")

    # --- FCF Yield ---
    if fcf is not None and market_cap is not None and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100
        results["fcf_yield"] = round(fcf_yield, 2)
        formulas["fcf_yield"] = f"({fcf:.2f}M FCF / {market_cap:.2f}M mkt_cap) × 100 = {fcf_yield:.2f}%"
    else:
        results["fcf_yield"] = None
        if market_cap is None:
            errors.append("WARN: fcf_yield cannot be computed — market_cap unavailable")
        elif fcf is None:
            errors.append("WARN: fcf_yield cannot be computed — FCF unavailable")

    # --- Gross Margin ---
    if gross_profit_ttm is not None and revenue_ttm is not None and revenue_ttm > 0:
        gm = (gross_profit_ttm / revenue_ttm) * 100
        results["gross_margin"] = round(gm, 2)
        formulas["gross_margin"] = f"({gross_profit_ttm}M / {revenue_ttm}M) × 100 = {gm:.2f}%"
    else:
        results["gross_margin"] = None
        if gross_profit_ttm is None:
            errors.append("WARN: gross_profit_ttm not provided — gross_margin cannot be computed")

    # --- Operating Margin ---
    if operating_income_ttm is not None and revenue_ttm is not None and revenue_ttm > 0:
        om = (operating_income_ttm / revenue_ttm) * 100
        results["operating_margin"] = round(om, 2)
        formulas["operating_margin"] = f"({operating_income_ttm}M / {revenue_ttm}M) × 100 = {om:.2f}%"
    else:
        results["operating_margin"] = None
        if operating_income_ttm is None:
            errors.append("WARN: operating_income_ttm not provided — operating_margin cannot be computed")

    # --- Net Margin ---
    if net_income_ttm is not None and revenue_ttm is not None and revenue_ttm > 0:
        nm = (net_income_ttm / revenue_ttm) * 100
        results["net_margin"] = round(nm, 2)
        formulas["net_margin"] = f"({net_income_ttm}M / {revenue_ttm}M) × 100 = {nm:.2f}%"
    else:
        results["net_margin"] = None
        if net_income_ttm is None or revenue_ttm is None:
            errors.append("WARN: net_margin cannot be computed — net_income_ttm or revenue_ttm missing")

    # --- Net Debt / EBITDA ---
    if ebitda_ttm is not None and ebitda_ttm > 0:
        nd_ebitda = net_debt / ebitda_ttm
        results["net_debt_ebitda"] = round(nd_ebitda, 2)
        formulas["net_debt_ebitda"] = f"{net_debt:.2f}M net_debt / {ebitda_ttm}M EBITDA = {nd_ebitda:.2f}x"
    else:
        results["net_debt_ebitda"] = None
        if ebitda_ttm is None:
            errors.append("WARN: net_debt_ebitda cannot be computed — ebitda_ttm missing")
        elif ebitda_ttm <= 0:
            errors.append("INFO: net_debt_ebitda not meaningful (EBITDA <= 0)")

    # --- Return ---
    output = {
        **results,
        "formulas": formulas,
        "errors": errors,
        "inputs_used": {k: v for k, v in inputs.items() if v is not None},
    }
    return output


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Financial ratio calculator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Path to input JSON file")
    group.add_argument("--inline", help="Inline JSON string")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            inputs = json.load(f)
    else:
        inputs = json.loads(args.inline)

    result = calculate_ratios(inputs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
