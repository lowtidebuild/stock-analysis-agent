from __future__ import annotations

import json

from scripts.run_mode_common import annotate_analysis_run_profile
from tools.quality_report import build_fixture_delivery_guard_item


def test_codex_native_run_profile_is_deterministic(tmp_path) -> None:
    analysis_path = tmp_path / "analysis-result.json"
    analysis_path.write_text(
        json.dumps(
            {
                "run_context": {
                    "backend": {
                        "provider": "codex_native",
                        "usage": {"api_calls": 0},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    profile = annotate_analysis_run_profile(
        analysis_path,
        allow_fixture_delivery=False,
        allow_deterministic_delivery=False,
        requested_run_profile=None,
    )
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    assert profile["run_profile"] == "deterministic"
    assert profile["deterministic_backend"] is True
    assert analysis["run_context"]["run_profile"] == "deterministic"
    assert analysis["run_context"]["verdict_provenance"] == "deterministic_rule"


def test_deterministic_delivery_guard_blocks_without_opt_in() -> None:
    item = build_fixture_delivery_guard_item(
        {
            "run_context": {
                "run_profile": "deterministic",
                "backend": {"provider": "codex_native"},
                "deterministic_backend": True,
            }
        }
    )

    assert item["status"] == "FAIL"
    assert item["severity"] == "BLOCKER"
    assert item["delivery_impact"] == "delivery_blocking_flag"
    assert item["blocker_action"] == "terminal"


def test_deterministic_delivery_guard_allows_explicit_opt_in_with_flag() -> None:
    item = build_fixture_delivery_guard_item(
        {
            "run_context": {
                "run_profile": "deterministic",
                "backend": {"provider": "codex_native"},
                "deterministic_backend": True,
                "allow_deterministic_delivery": True,
            }
        }
    )

    assert item["status"] == "PASS_WITH_FLAGS"
    assert item["severity"] == "MINOR"
    assert item["delivery_impact"] == "non_blocking_flag"
    assert item["blocker_action"] == "none"


def test_fixture_delivery_guard_behavior_is_unchanged() -> None:
    item = build_fixture_delivery_guard_item(
        {
            "run_context": {
                "run_profile": "smoke",
                "backend": {"provider": "fixture"},
                "fixture_backend": True,
            }
        }
    )

    assert item["status"] == "FAIL"
    assert item["severity"] == "BLOCKER"
    assert item["blocker_action"] == "terminal"
