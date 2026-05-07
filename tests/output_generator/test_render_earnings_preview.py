"""Mode E Preview renderer tests (Phase F.4).

Verifies the Preview renderer covers all 6 sections, OD-F2 backward compat
(options unavailable stub), Korean output by default, disclaimers,
source-tag coverage, and resilience against minimal/missing data.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "output-generator"
    / "scripts"
    / "render-earnings.py"
)


def load_render_module():
    spec = importlib.util.spec_from_file_location("render_earnings", RENDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_earnings"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_preview_analysis(*, options_available: bool = True, history_quarters: int = 6,
                          key_questions_count: int = 4,
                          language: str = "ko",
                          confirmed: bool = True) -> dict[str, Any]:
    """Realistic GOOGL Q1 2026 Preview fixture (D-3)."""
    options = {
        "status": "available",
        "spot_price": 388.43,
        "atm_strike": 388,
        "atm_call_price": 4.20,
        "atm_put_price": 4.05,
        "atm_straddle_price": 8.25,
        "implied_move_pct": 2.12,
        "iv_percentile": None,
        "nearest_expiry": "2026-05-02",
        "tag": "[Options]",
    }
    if not options_available:
        options = {
            "status": "unavailable",
            "_unavailable_reason": "yfinance option chain not available for this ticker",
            "tag": "[Options]",
        }

    quarters = []
    for i in range(history_quarters):
        quarters.append({
            "quarter": f"Q{(i % 4) + 1} {2024 + (i // 4)}",
            "report_date": f"2025-0{1 + (i % 4)}-30",
            "actual_eps": round(2.0 + 0.05 * i, 2),
            "consensus_eps": round(1.95 + 0.05 * i, 2),
            "surprise_pct": round(2.5 + 0.4 * i, 1),
            "beat": True,
            "stock_reaction_1d_pct": round(1.0 + 0.5 * i, 1),
            "tag": "[History]",
        })

    questions = [
        {
            "question": "Cloud +63% 모멘텀 유지될까?",
            "expected_answer": "Yes",
            "stock_impact_if_yes": "+3 to +5%",
            "stock_impact_if_no": "-8 to -10%",
            "rationale": "Q4 +63% YoY는 컨센서스(35%) 대비 +28pp 서프라이즈.",
            "mechanism": "Cloud miss → Cloud margin 압축 → Sum-of-parts EV 하향 → 12M target -8~10%",
        },
        {
            "question": "FY26 Capex $180-190B 가이던스 유지?",
            "expected_answer": "Yes",
            "stock_impact_if_yes": "±1%",
            "stock_impact_if_no": "-4 to -6%",
            "rationale": "Capex 상향 시 FCF 압박 가시화.",
            "mechanism": "Capex 상향 → FCF -8% → DCF fair value -7% → 단기 multiple 하향",
        },
        {
            "question": "Search 광고 매출 +11% 컨센서스 달성?",
            "expected_answer": "Yes",
            "stock_impact_if_yes": "+1 to +2%",
            "stock_impact_if_no": "-3 to -4%",
            "rationale": "Search 광고는 GOOGL EBIT의 60%+ 차지.",
            "mechanism": "Search miss → 영업이익 가이던스 하향 → forward EPS -3% → P/E re-rating",
        },
        {
            "question": "YouTube AI 광고 전환율 회복세?",
            "expected_answer": "Partial",
            "stock_impact_if_yes": "+1 to +3%",
            "stock_impact_if_no": "-2 to -4%",
            "rationale": "YouTube ad는 Q4 +14% 성장으로 회복 신호.",
            "mechanism": "YouTube CTR 회복 → ARPU 증가 → 매출 +2% → 시총 +1~3%",
        },
    ][:key_questions_count]

    return {
        "ticker": "GOOGL",
        "company_name": "Alphabet Inc Class A",
        "currency": "USD",
        "data_mode": "enhanced",
        "output_mode": "E",
        "earnings_sub_mode": "preview",
        "earnings_window": {
            "next_earnings_date": "2026-04-29",
            "next_earnings_confirmed": confirmed,
            "days_until": -3,
            "window_label": "D-3",
        },
        "output_language": language,
        "analysis_date": "2026-04-26",
        "price_at_analysis": 384.20,
        "consensus_snapshot": {
            "eps": {
                "mean": 2.62, "high": 2.71, "low": 2.55, "median": 2.62,
                "tag": "[Est]",
            },
            "revenue": {
                "mean": 109200, "high": 110800, "low": 107900, "median": 109150,
                "unit": "millions_usd", "tag": "[Est]",
            },
            "segment_consensus": [
                {"segment": "Cloud", "metric": "rev_yoy_pct", "mean": 35, "high": 50, "low": 28, "tag": "[Est]"},
                {"segment": "Search", "metric": "rev_yoy_pct", "mean": 11, "high": 14, "low": 8, "tag": "[Est]"},
                {"segment": "YouTube", "metric": "rev_yoy_pct", "mean": 13, "high": 17, "low": 9, "tag": "[Est]"},
            ],
        },
        "beat_miss_history": {
            "quarters": quarters,
            "summary": {
                "hit_rate": 0.875,
                "avg_surprise_pct": 12.4,
                "avg_reaction_1d_pct": 3.2,
                "tag": "[Calc]",
            },
        },
        "key_questions": questions,
        "options_snapshot": options,
        "pre_mortem": [
            {"scenario": "Cloud miss", "trigger": "Cloud growth ≤ +45% YoY",
             "stock_impact": "-8%", "probability": 0.20,
             "mechanism": "Cloud margin contraction → SOTP EV 하향 → fwd P/E 하향"},
            {"scenario": "Capex shock", "trigger": "FY26 capex 가이던스 $200B 초과",
             "stock_impact": "-5%", "probability": 0.25,
             "mechanism": "FCF 압축 → DCF fair value -7% → 단기 multiple 하향"},
            {"scenario": "In-line / mild beat", "trigger": "EPS surprise ≤ 5%, guidance 유지",
             "stock_impact": "±2%", "probability": 0.40,
             "mechanism": "옵션 시장 implied move(±2.1%) 안에서 흡수"},
            {"scenario": "Strong beat + raise", "trigger": "EPS surprise > 10% AND guidance 상향",
             "stock_impact": "+5 to +7%", "probability": 0.15,
             "mechanism": "Forward EPS 컨센서스 +5% → multiple 재평가"},
        ],
        "pre_print_position": {
            "recommendation": "Hold",
            "rationale": (
                "Implied move ±2.1%는 historical avg reaction 3.2% 보다 좁음. "
                "Asymmetric downside (cloud miss -8% vs upside +5%) 고려 시 add 매력도 낮음."
            ),
            "options_strategy": (
                "Catalyst-driven traders: nearest-expiry ATM straddle ($8.25) — "
                "implied move 도달 시 break-even, cloud miss/beat 양쪽 모두 수익."
            ),
        },
        "report_path": "output/reports/GOOGL_E_preview_ko_2026-04-26.html",
    }


class RenderEarningsPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render = load_render_module()

    def test_hero_contains_ticker_and_d_minus_badge_and_consensus_eps(self) -> None:
        """Test 1: Hero contains ticker + D-N badge + consensus EPS."""
        analysis = make_preview_analysis()
        html = self.render.build_preview_html(analysis)
        self.assertIn("GOOGL", html, "ticker missing from hero")
        self.assertIn("D-3", html, "D-N window badge missing")
        self.assertIn("2.62", html, "consensus EPS mean missing from hero")

    def test_all_six_sections_rendered_with_full_data(self) -> None:
        """Test 2: All 6 sections rendered when full data present."""
        analysis = make_preview_analysis()
        html = self.render.build_preview_html(analysis)
        for section_id in [
            "section-consensus",
            "section-history",
            "section-key-questions",
            "section-options",
            "section-pre-mortem",
            "section-pre-print",
        ]:
            self.assertIn(
                section_id, html,
                f"section id `{section_id}` missing from rendered HTML",
            )

    def test_options_unavailable_renders_stub_not_raw_data(self) -> None:
        """Test 3: OD-F2 — options_snapshot.status='unavailable' shows stub."""
        analysis = make_preview_analysis(options_available=False)
        html = self.render.build_preview_html(analysis)
        # Stub markers must appear
        self.assertIn("데이터 미수집", html, "options unavailable stub missing")
        self.assertIn(
            "options chain unavailable", html,
            "options unavailable reason caption missing",
        )
        # Raw available-only fields must NOT appear
        self.assertNotIn("ATM Straddle", html,
                         "ATM Straddle should not render when status=unavailable")
        self.assertNotIn("Implied 1-day Move", html,
                         "Implied 1-day Move tile should not render when unavailable")

    def test_missing_beat_miss_history_renders_gracefully(self) -> None:
        """Test 4: Missing beat_miss_history → Section 2 omitted gracefully."""
        analysis = make_preview_analysis()
        analysis["beat_miss_history"] = {"quarters": [], "summary": {}}
        # Should not raise
        html = self.render.build_preview_html(analysis)
        # Either omits the chart canvas or shows graceful banner
        self.assertIn("Data unavailable", html,
                      "must surface 'Data unavailable' banner when no quarters")

    def test_empty_key_questions_renders_gracefully(self) -> None:
        """Test 5: Empty key_questions → Section 3 renders gracefully."""
        analysis = make_preview_analysis(key_questions_count=0)
        analysis["key_questions"] = []
        # Renderer must not crash and must surface a quality flag
        html = self.render.build_preview_html(analysis)
        # Section 3 should either be omitted or surface a quality flag banner
        self.assertTrue(
            "no key questions" in html.lower() or "Quality flag" in html,
            "must surface quality flag for empty key_questions",
        )

    def test_korean_output_renders_korean_section_titles(self) -> None:
        """Test 6: Korean output (output_language='ko') — section titles in Korean."""
        analysis = make_preview_analysis(language="ko")
        html = self.render.build_preview_html(analysis)
        self.assertIn("컨센서스 스냅샷", html)
        self.assertIn("핵심 질문", html)
        self.assertIn("Pre-Mortem", html)
        self.assertIn("Pre-Print 포지션", html)
        # Korean font link must be in head
        self.assertIn("Noto+Sans+KR", html,
                      "Korean Noto Sans KR font missing for ko output")

    def test_disclaimer_and_source_tag_coverage(self) -> None:
        """Test 7: Disclaimer present, source tag coverage ≥80%."""
        analysis = make_preview_analysis()
        html = self.render.build_preview_html(analysis)
        # Disclaimer
        self.assertIn("Disclaimer", html)
        self.assertIn("not investment advice", html.lower())
        # Source tags coverage — must surface at least the canonical tag set
        for tag in ["[Est]", "[Options]", "[History]", "[Calc]"]:
            self.assertIn(tag, html, f"source tag {tag} missing")

    def test_minimal_analysis_renders_without_crash(self) -> None:
        """Test 8: Backward compat — minimal analysis without optional fields renders."""
        minimal = {
            "ticker": "AAPL",
            "company_name": "Apple Inc",
            "currency": "USD",
            "output_mode": "E",
            "earnings_sub_mode": "preview",
            "output_language": "ko",
            "analysis_date": "2026-05-01",
            "price_at_analysis": 200.0,
            "earnings_window": {
                "next_earnings_date": "2026-05-08",
                "next_earnings_confirmed": False,
                "days_until": -7,
                "window_label": "D-7",
            },
            "consensus_snapshot": {
                "eps": {"mean": 2.10, "tag": "[Est]"},
                "revenue": {"mean": 95000, "unit": "millions_usd", "tag": "[Est]"},
            },
            # No beat_miss_history, no key_questions, no options, no pre_mortem
        }
        # Must not raise
        html = self.render.build_preview_html(minimal)
        self.assertIn("AAPL", html)
        self.assertIn("D-7", html)
        # Confirmed warning banner shown when not confirmed
        self.assertIn("미확정", html)

    def test_script_injection_in_quarter_label_is_neutralized(self) -> None:
        """B1 regression — a `quarter` value containing `</script>` must not
        prematurely close the embedded <script> blocks (chart data island
        + Chart.js init). Per CLAUDE.md §12, fetched fields are untrusted.

        Baseline (no attack) has 4 opens / 4 closes:
          - 2 CDN <script src=...></script> in <head>
          - 1 <script id="beat-miss-chart-data" type="application/json">…</script>
          - 1 <script>(function(){ Chart… })()</script> chart-init at the end

        With the attacker payload sanitized, the count of *closing* `</script>`
        tags must remain at 4. If the helper is removed, the JSON-embedded
        `</script>` from the attacker's payload will appear unescaped twice
        (chart data island + chart init), pushing the close count to 6 and
        prematurely terminating the surrounding <script> blocks.
        """
        # Baseline: count closes in clean output.
        baseline_html = self.render.build_preview_html(make_preview_analysis())
        baseline_closes = baseline_html.count("</script>")

        # Inject a malicious quarter label as the first quarter.
        analysis = make_preview_analysis()
        attack = 'Q1 </script><script>alert("xss")</script>'
        analysis["beat_miss_history"]["quarters"][0]["quarter"] = attack
        html = self.render.build_preview_html(analysis)

        # 1) The escaped sentinel `<\/script>` must appear (proof the helper
        #    ran on JSON serialization for <script> blocks).
        self.assertIn("<\\/script>", html,
                      "escaped <\\/script> sentinel missing — helper not applied")

        # 2) The number of *closing* `</script>` tags is unchanged from the
        #    baseline. A successful injection would add at least one extra
        #    `</script>` per embed site (2 sites: chart data island + chart
        #    init).
        attack_closes = html.count("</script>")
        self.assertEqual(
            attack_closes, baseline_closes,
            f"attacker payload added {attack_closes - baseline_closes} extra "
            f"</script> tags — script injection still possible",
        )

        # 3) The escaped attacker payload still appears as visible text in
        #    the rendered table cell (HTML-escaped via `escape()`), so the
        #    user can see the malformed quarter value rather than executing
        #    it. (`html.escape` produces `&lt;/script&gt;`.)
        self.assertIn("&lt;/script&gt;", html,
                      "attacker payload should appear HTML-escaped in table cell")

    def test_dispatch_renders_preview_path(self) -> None:
        """Dispatch sanity — render_earnings routes preview correctly."""
        analysis = make_preview_analysis()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "GOOGL_E_preview_ko_2026-04-26.html"
            written = self.render.render_earnings(analysis, output_path=str(out_path))
            self.assertEqual(Path(written), out_path)
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("EARNINGS PREVIEW", content)


if __name__ == "__main__":
    unittest.main()
