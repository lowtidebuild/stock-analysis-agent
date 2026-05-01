# Reverse DCF Implementation Plan

> **Status:** Revised after verification on 2026-04-30.
>
> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

Add reverse DCF support to `.claude/agents/analyst/scripts/dcf-calculator.py`.

Given a current stock price, the calculator solves for the annual FCF growth rate implied by the market price. The result is written into the existing `sections.dcf_analysis.reverse` block for Mode C/D outputs and rendered beside the forward DCF.

## Corrected Contract

The implementation uses the existing calculator interface:
- `--input <json_file>`
- `--inline '<json>'`
- `--schema`

There is **no separate `--reverse` CLI mode in v1**. Reverse DCF runs when the input contains `current_price_for_reverse`. This avoids adding a second execution path and keeps the current inline/file interface stable.

Current `compute_dcf()` returns:

```python
(results_dict, errors_list)
```

All tests and implementation must respect that tuple contract.

## Files

Create:
- `tests/test_dcf_reverse.py`

Modify:
- `.claude/agents/analyst/scripts/dcf-calculator.py`
- `.claude/agents/analyst/AGENT.md`
- `references/analysis-framework-dashboard.md`
- `references/analysis-framework-memo.md`
- `.claude/skills/dashboard-generator/references/html-template.md`

Do not modify:
- `.claude/schemas/analysis-result.schema.json` unless validation proves necessary. The top-level schema allows additional properties under `sections`.
- quality-checker logic.

## Mathematical Contract

Forward DCF:

```text
compute_dcf(fcf_growth_rate, ...)
  -> fair_value_per_share
```

Reverse DCF:

```text
solve_implied_growth(target_price, fcf_ttm, wacc, terminal_growth_rate,
                     forecast_years, net_debt, diluted_shares)
  -> reverse_dcf result object
```

Result statuses:

| Status | Meaning |
|---|---|
| `success` | Solver found an implied FCF growth rate. |
| `exceeds_ceiling` | Target price requires growth above the configured ceiling. |
| `below_floor` | Target price is below the fair value at terminal-growth-plus-offset. |
| `wacc_invalid` | WACC is missing or not greater than terminal growth. |
| `negative_fcf` | FCF TTM is zero or negative. |
| `invalid_input` | Target price or diluted shares are missing/non-positive. |
| `did_not_converge` | Bisection failed within max iterations. |

Bounds:
- Lower bound: `terminal_growth_rate + 0.001`
- Upper bound: `1.0`
- Growth-rate interval tolerance: `0.0005` (5bp)
- Max iterations: `50`

## Task 1 - Write Tests First

Create `tests/test_dcf_reverse.py`.

Important: `compute_dcf()` returns `(result, errors)`, not just `result`.

```python
"""Tests for reverse DCF implied FCF growth."""
import importlib.util
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DCF_PATH = REPO_ROOT / ".claude/agents/analyst/scripts/dcf-calculator.py"

spec = importlib.util.spec_from_file_location("dcf_calculator", DCF_PATH)
dcf = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dcf
spec.loader.exec_module(dcf)


BASE_INPUTS = {
    "fcf_ttm": 1000.0,
    "fcf_growth_rate": 0.20,
    "wacc": 0.11,
    "terminal_growth_rate": 0.025,
    "forecast_years": 10,
    "net_debt": 0,
    "diluted_shares": 100.0,
}


def test_solve_implied_growth_recovers_input_growth():
    forward, errors = dcf.compute_dcf(**BASE_INPUTS)
    assert forward is not None, errors
    target_price = forward["fair_value_per_share"]

    implied = dcf.solve_implied_growth(
        target_price=target_price,
        fcf_ttm=BASE_INPUTS["fcf_ttm"],
        wacc=BASE_INPUTS["wacc"],
        terminal_growth_rate=BASE_INPUTS["terminal_growth_rate"],
        forecast_years=BASE_INPUTS["forecast_years"],
        net_debt=BASE_INPUTS["net_debt"],
        diluted_shares=BASE_INPUTS["diluted_shares"],
    )

    assert implied["status"] == "success"
    assert abs(implied["implied_fcf_growth"] - 0.20) < 0.005
    assert implied["iterations"] <= 50


def test_implied_growth_exceeds_ceiling():
    inputs = {k: v for k, v in BASE_INPUTS.items() if k != "fcf_growth_rate"}
    forward_max, errors = dcf.compute_dcf(fcf_growth_rate=1.0, **inputs)
    assert forward_max is not None, errors
    out = dcf.solve_implied_growth(
        target_price=forward_max["fair_value_per_share"] * 100,
        **inputs,
    )
    assert out["status"] == "exceeds_ceiling"
    assert out["implied_fcf_growth"] is None


def test_implied_growth_below_floor():
    inputs = {k: v for k, v in BASE_INPUTS.items() if k != "fcf_growth_rate"}
    floor, errors = dcf.compute_dcf(fcf_growth_rate=0.026, **inputs)
    assert floor is not None, errors
    out = dcf.solve_implied_growth(
        target_price=floor["fair_value_per_share"] * 0.5,
        **inputs,
    )
    assert out["status"] == "below_floor"
    assert out["implied_fcf_growth"] is None


def test_implied_growth_negative_fcf():
    out = dcf.solve_implied_growth(
        target_price=100.0,
        fcf_ttm=-500.0,
        wacc=0.11,
        terminal_growth_rate=0.025,
        forecast_years=10,
        net_debt=0,
        diluted_shares=100.0,
    )
    assert out["status"] == "negative_fcf"
    assert out["implied_fcf_growth"] is None


def test_implied_growth_wacc_below_terminal():
    out = dcf.solve_implied_growth(
        target_price=100.0,
        fcf_ttm=1000.0,
        wacc=0.02,
        terminal_growth_rate=0.025,
        forecast_years=10,
        net_debt=0,
        diluted_shares=100.0,
    )
    assert out["status"] == "wacc_invalid"


def test_calculate_dcf_includes_reverse_block_when_price_provided():
    inputs = {
        "scenario_name": "base",
        "current_price": 100.0,
        "current_price_for_reverse": 100.0,
        **BASE_INPUTS,
    }
    out = dcf.calculate_dcf(inputs)
    assert "reverse_dcf" in out
    assert out["reverse_dcf"]["target_price"] == 100.0
```

Run initial failure:

```bash
PYTHONPATH=. python3 -m pytest tests/test_dcf_reverse.py -v
```

Expected before implementation:
- failure because `solve_implied_growth` does not exist.

Expected after implementation:
- `6 passed`.

## Task 2 - Implement `solve_implied_growth()`

Add below `compute_dcf()` and before `build_sensitivity_table()`.

Implementation requirements:
- Call `compute_dcf()` and unpack `(result, errors)`.
- Use `invalid_input` for missing/non-positive target price or diluted shares.
- Use `negative_fcf` for `fcf_ttm <= 0`.
- Use `wacc_invalid` for `wacc <= terminal_growth_rate`.
- Store `bracket_low`, `bracket_high`, `fair_value_at_floor`, `fair_value_at_ceiling`.
- Return `implied_fcf_growth` rounded to 4 decimals only on success.
- Use interval width `< tolerance` where default `tolerance=0.0005`.

Skeleton:

```python
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
        return {**base, "status": "wacc_invalid", "notes": "WACC must exceed terminal growth."}
    if fcf_ttm is None or fcf_ttm <= 0:
        return {**base, "status": "negative_fcf", "notes": "Reverse DCF requires positive FCF TTM."}
    if target_price is None or target_price <= 0 or diluted_shares is None or diluted_shares <= 0:
        return {**base, "status": "invalid_input", "notes": "Target price and diluted shares must be positive."}

    def fair_at(growth):
        result, errors = compute_dcf(
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
        return {**base, "status": "did_not_converge", "notes": "DCF failed at bracket bounds."}
    if target_price > fair_high:
        return {**base, "status": "exceeds_ceiling", "notes": "Target price requires growth above ceiling."}
    if target_price < fair_low:
        return {**base, "status": "below_floor", "notes": "Target price is below floor-growth DCF value."}

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        mid = (low + high) / 2
        fair_mid = fair_at(mid)
        if fair_mid is None:
            return {**base, "status": "did_not_converge", "iterations": iterations, "notes": "DCF failed mid-bisection."}
        if fair_mid < target_price:
            low = mid
        else:
            high = mid
        if (high - low) < tolerance:
            implied = round((low + high) / 2, 4)
            return {**base, "status": "success", "implied_fcf_growth": implied, "iterations": iterations, "notes": f"Converged in {iterations} iterations."}

    return {**base, "status": "did_not_converge", "iterations": iterations, "notes": f"Bisection did not converge in {max_iterations} iterations."}
```

## Task 3 - Wire Into `calculate_dcf()`

Add input schema:

```python
"current_price_for_reverse": {
    "type": "float",
    "required": False,
    "description": "If provided, solve for market-implied annual FCF growth at this stock price.",
    "default": None,
},
```

Add output schema:

```python
"reverse_dcf": "dict or null — implied FCF growth result when current_price_for_reverse is provided",
```

After forward DCF succeeds, compute:

```python
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
    result_payload["reverse_dcf"] = implied
```

Do not use truthiness guards like `if current_price_for_reverse and fcf_ttm`.

## Task 4 - CLI Smoke Tests

Schema:

```bash
python3 .claude/agents/analyst/scripts/dcf-calculator.py --schema
```

Expected:
- `input_fields.current_price_for_reverse` exists
- `output_fields.reverse_dcf` exists

Inline:

```bash
python3 .claude/agents/analyst/scripts/dcf-calculator.py --inline '{
  "scenario_name": "base",
  "current_price": 137.97,
  "current_price_for_reverse": 137.97,
  "diluted_shares": 2573.497,
  "fcf_ttm": 2100.591,
  "fcf_growth_rate": 0.28,
  "wacc": 0.13,
  "terminal_growth_rate": 0.030,
  "forecast_years": 10,
  "net_debt": -1194.46
}'
```

Expected:
- JSON output includes `reverse_dcf`
- `reverse_dcf.status` is one of the documented statuses
- If `status == "success"`, `implied_fcf_growth`, `analyst_growth_assumption`, and `growth_gap_bp` exist

## Task 5 - Analyst and Framework Docs

Modify `.claude/agents/analyst/AGENT.md`:

- [ ] Mode C/D DCF step: always pass `current_price_for_reverse` for the Base scenario when current price is available.
- [ ] Write the calculator's `reverse_dcf` result to `sections.dcf_analysis.reverse`.
- [ ] Omit the rendered reverse DCF block for `wacc_invalid`, `negative_fcf`, and `invalid_input`.
- [ ] Render `exceeds_ceiling` and `below_floor` as explicit status banners, not empty placeholders.

Modify `references/analysis-framework-dashboard.md` and `references/analysis-framework-memo.md`:

- [ ] Add "Reverse DCF / Expectations Investing" under the DCF section.
- [ ] Explain it as a transparency tool, not a standalone verdict.
- [ ] Use output language appropriate labels in generated reports.

Modify `.claude/skills/dashboard-generator/references/html-template.md`:

- [ ] Add optional block after the DCF sensitivity table.
- [ ] Render only when `sections.dcf_analysis.reverse` exists.
- [ ] Avoid emoji in the template unless the surrounding template already uses them.

## Definition of Done

- [ ] `PYTHONPATH=. python3 -m pytest tests/test_dcf_reverse.py -v` returns `6 passed`.
- [ ] `dcf-calculator.py --schema` shows `current_price_for_reverse` and `reverse_dcf`.
- [ ] Inline smoke test returns a documented `reverse_dcf.status`.
- [ ] Analyst docs instruct Mode C/D to pass `current_price_for_reverse` in Base scenario.
- [ ] Dashboard and memo frameworks describe reverse DCF rendering.
- [ ] Existing DCF behavior without `current_price_for_reverse` is unchanged.

## Out of Scope

- Reverse DCF for Bull/Bear scenarios.
- Reverse DCF WACC sensitivity table.
- Mode A briefing integration.
- EV/Sales or P/E reverse valuation.

