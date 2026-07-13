"""Rendered-output proximity scan for excluded metrics (blank-over-wrong).

The JSON-level check only catches an excluded metric re-appearing in
``analysis-result.key_metrics``. The rendered scan additionally flags a
numeric value sitting next to the excluded metric's display label in the
rendered HTML — the fabrication surface the JSON check cannot see.

Scan findings are heuristic, so on their own they are MAJOR
(delivered-with-flag), never BLOCKER.
"""

from __future__ import annotations

from pathlib import Path

from tools.quality_report import build_blank_over_wrong_item


VALIDATED = {
    "exclusions": [
        {
            "metric": "net_debt_ebitda",
            "exclusion_reason": "sources differ by 22%",
        }
    ]
}
ANALYSIS = {"key_metrics": {"net_debt_ebitda": {"value": None, "grade": "D"}}}


def _write_report(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "TEST_C_ko_2026-07-13.html"
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    return path


def test_number_next_to_excluded_metric_label_is_flagged_major(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        '<div><p>Net Debt / EBITDA</p><p class="value">2.5x</p></div>',
    )

    item = build_blank_over_wrong_item(VALIDATED, ANALYSIS, report_path=report)

    assert item["status"] == "FAIL"
    assert item["rendered_scan"]["scanned"] is True
    assert item["rendered_scan"]["findings"], item
    assert item["rendered_scan"]["findings"][0]["metric"] == "net_debt_ebitda"
    # Heuristic finding alone must not block delivery.
    assert item["severity"] == "MAJOR"
    assert item["blocker_action"] == "none"
    assert any("net_debt_ebitda" in error for error in item["errors"])


def test_blank_dash_before_neighbor_number_passes(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        "<tr><td>Net Debt / EBITDA</td><td>—</td><td>2.5x</td></tr>",
    )

    item = build_blank_over_wrong_item(VALIDATED, ANALYSIS, report_path=report)

    assert item["status"] == "PASS", item
    assert item["rendered_scan"]["scanned"] is True
    assert item["rendered_scan"]["findings"] == []


def test_bare_year_near_label_is_not_a_finding(tmp_path: Path) -> None:
    # Bare integers (years, counts) carry no currency prefix or unit suffix
    # and must not trip the scan.
    report = _write_report(
        tmp_path,
        "<p>Net Debt / EBITDA data unavailable as of 2026</p>",
    )

    item = build_blank_over_wrong_item(VALIDATED, ANALYSIS, report_path=report)

    assert item["status"] == "PASS", item


def test_no_report_path_keeps_json_only_behavior() -> None:
    item = build_blank_over_wrong_item(VALIDATED, ANALYSIS, report_path=None)

    assert item["status"] == "PASS"
    assert item["rendered_scan"] == {"scanned": False, "findings": []}


def test_json_violation_still_blocker_when_scan_also_fires(tmp_path: Path) -> None:
    analysis = {"key_metrics": {"net_debt_ebitda": {"value": 2.5, "grade": "C"}}}
    report = _write_report(
        tmp_path,
        "<div><p>Net Debt / EBITDA</p><p>2.5x</p></div>",
    )

    item = build_blank_over_wrong_item(VALIDATED, analysis, report_path=report)

    assert item["status"] == "FAIL"
    assert item["violations_found"] == 1
    # JSON violation present -> no explicit severity downgrade; the default
    # inference keeps blank_over_wrong FAIL as a patchable BLOCKER.
    assert "severity" not in item
