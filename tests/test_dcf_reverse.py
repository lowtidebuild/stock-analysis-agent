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
