from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALYST_PATH = ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "catalyst-aggregator.py"

spec = importlib.util.spec_from_file_location("catalyst_aggregator", CATALYST_PATH)
catalyst = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = catalyst
assert spec and spec.loader
spec.loader.exec_module(catalyst)


def test_catalyst_record_has_category_impact_and_preannounce_defaults():
    rec = catalyst.build_catalyst_record(
        {
            "ticker": "AAPL",
            "date": "2026-07-31",
            "event": "Q3 earnings",
            "source": "[Filing]",
        }
    )

    assert rec["category"] == "Earnings"
    assert rec["impact"] == "H"
    assert rec["pre_announce_risk"] is False


def test_catalyst_category_classifies_macro_events():
    assert catalyst.classify_category("FOMC rate decision") == "Macro"
    assert catalyst.classify_impact("industry data release") == "L"
