from __future__ import annotations

from tools.artifact_validation import validate_analysis_semantics
from tools.quality_report import build_scenario_consistency_item


def _analysis(bear_return: float) -> dict:
    price = 100.0
    bull_return = 30.0
    base_return = 10.0
    bull_probability = 0.25
    base_probability = 0.50
    bear_probability = 0.25
    rr_score = (
        (bull_return * bull_probability) + (base_return * base_probability)
    ) / abs(bear_return * bear_probability)
    return {
        "price_at_analysis": price,
        "scenarios": {
            "bull": {
                "target": 130.0,
                "return_pct": bull_return,
                "probability": bull_probability,
            },
            "base": {
                "target": 110.0,
                "return_pct": base_return,
                "probability": base_probability,
            },
            "bear": {
                "target": price * (1 + bear_return / 100),
                "return_pct": bear_return,
                "probability": bear_probability,
            },
        },
        "rr_score": rr_score,
    }


def test_positive_bear_return_is_rejected() -> None:
    errors = validate_analysis_semantics(_analysis(2.0))

    assert any("$.scenarios.bear" in error and "must be negative" in error for error in errors)


def test_zero_bear_return_explains_rr_skip() -> None:
    analysis = _analysis(-15.0)
    analysis["scenarios"]["bear"]["target"] = 100.0
    analysis["scenarios"]["bear"]["return_pct"] = 0.0

    errors = validate_analysis_semantics(analysis)

    assert any("cannot verify rr_score because bear return is zero" in error for error in errors)


def test_shallow_bear_return_is_major() -> None:
    analysis = _analysis(-3.0)

    errors = validate_analysis_semantics(analysis)
    item = build_scenario_consistency_item(analysis)

    assert any("shallow bear" in error for error in errors)
    assert item["status"] == "FAIL"
    assert item["severity"] == "MAJOR"


def test_material_bear_return_passes_guard() -> None:
    errors = validate_analysis_semantics(_analysis(-15.0))

    assert not any("$.scenarios.bear" in error for error in errors)
