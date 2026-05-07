"""Mode E Review renderer tests (Phase F.4).

Verifies the Review renderer covers all 6 sections, OD-F3 outdated verdict
styling, Mode C rerun banner, beat/miss color coding, no-prior-Mode-C
backward compat, Korean output, disclaimers, and resilience to missing data.
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


def make_review_analysis(
    *,
    beat: bool = True,
    has_prior_mode_c: bool = True,
    outdated: bool = True,
    rerun_recommended: bool = True,
    has_stock_reaction: bool = True,
    language: str = "ko",
) -> dict[str, Any]:
    """Realistic GOOGL Q1 2026 Review fixture (D+1)."""
    eps_actual = 5.11 if beat else 1.95
    eps_consensus = 2.63
    eps_surprise = round((eps_actual - eps_consensus) / abs(eps_consensus) * 100, 1)
    rev_actual = 109930
    rev_consensus = 109200
    rev_surprise = round((rev_actual - rev_consensus) / abs(rev_consensus) * 100, 1)

    stock_reaction: dict[str, Any]
    if has_stock_reaction:
        stock_reaction = {
            "post_market_pct": 4.2 if beat else -3.1,
            "next_day_pct": 6.5 if beat else -5.8,
            "next_2day_pct": None,
            "tag": "[Portal]",
        }
    else:
        stock_reaction = {"post_market_pct": None, "next_day_pct": None, "tag": "[Portal]"}

    thesis_impact: dict[str, Any]
    if has_prior_mode_c:
        thesis_impact = {
            "prior_mode_c_date": "2026-04-15",
            "prior_mode_c_path": "output/data/GOOGL/snapshots/20260415-mode-c/analysis-result.json",
            "long_pillars": [
                {"pillar": "Cloud 성장 모멘텀", "prior_status": "On track",
                 "current_status": "Strengthened", "trend": "Positive",
                 "evidence": "Q1 +63% (컨센서스 +35% 대비 +28pp 초과)"},
                {"pillar": "광고 매출 안정성", "prior_status": "On track",
                 "current_status": "On track", "trend": "Stable",
                 "evidence": "Search +12% YoY 컨센서스 대비 부합"},
            ],
            "short_pillars": [
                {"pillar": "Capex 부담 → FCF 압박", "prior_status": "Watching",
                 "current_status": "Weakened", "trend": "Negative",
                 "evidence": "FY26 capex $180-190B (전년비 +20%), FCF -8% 압박"},
            ],
        }
    else:
        thesis_impact = {
            "prior_mode_c_date": None,
            "long_pillars": [],
            "short_pillars": [],
        }

    light_verdict: dict[str, Any]
    if has_prior_mode_c:
        light_verdict = {
            "prior_rr_score": 1.69,
            "updated_rr_score": None,
            "prior_verdict": "관찰",
            "updated_verdict": "관찰",
            "reason": (
                "Forward EPS 컨센서스 +5.6% (12.50 → 13.20). Bull/Base/Bear target 유지 "
                "(DCF 미재실행). Cloud growth pillar 강화는 Bull 시나리오 가중치를 높이지만 "
                "capex 부담이 Bear 시나리오 트리거를 유지시켜 net R/R 중립."
            ),
            "outdated_flag": outdated,
            "mode_c_rerun_recommended": rerun_recommended,
            "rerun_window": "D+2 ~ D+5",
        }
    else:
        light_verdict = {
            "prior_rr_score": None,
            "updated_rr_score": None,
            "prior_verdict": None,
            "updated_verdict": None,
            "reason": "이전 Mode C 분석이 없어 R/R Score 비교가 불가능합니다.",
            "outdated_flag": False,
            "mode_c_rerun_recommended": rerun_recommended,
            "rerun_window": "D+2 ~ D+5",
        }

    return {
        "ticker": "GOOGL",
        "company_name": "Alphabet Inc Class A",
        "currency": "USD",
        "data_mode": "enhanced",
        "output_mode": "E",
        "earnings_sub_mode": "review",
        "earnings_window": {
            "actual_earnings_date": "2026-04-29",
            "days_since": 1,
            "window_label": "D+1",
        },
        "output_language": language,
        "analysis_date": "2026-04-30",
        "price_at_analysis": 408.50,
        "actual_vs_consensus": {
            "eps": {"actual": eps_actual, "consensus": eps_consensus,
                    "surprise_pct": eps_surprise, "beat": beat, "tag": "[Company]"},
            "revenue": {"actual": rev_actual, "consensus": rev_consensus,
                        "surprise_pct": rev_surprise, "beat": True,
                        "unit": "millions_usd", "tag": "[Company]"},
            "segments": [
                {"segment": "Cloud", "metric": "rev_yoy_pct", "actual": 63,
                 "consensus": 35, "beat": True, "tag": "[Company]"},
                {"segment": "Search", "metric": "rev_yoy_pct", "actual": 12,
                 "consensus": 11, "beat": True, "tag": "[Company]"},
            ],
            "operating_margin": {"actual": 0.34, "consensus": 0.32,
                                 "delta_pp": 2, "beat": True, "tag": "[Filing]"},
        },
        "stock_reaction": stock_reaction,
        "guidance_delta": {
            "fy_eps_consensus_pre": 12.50,
            "fy_eps_consensus_post": 13.20,
            "delta_pct": 5.6,
            "tone": "raised",
            "company_guidance_change": "FY26 capex raised to $180-190B from $175-185B",
            "tag": "[Est]",
        },
        "key_questions_answered": [
            {"question": "Cloud +63% 모멘텀 유지될까?", "answer_status": "yes",
             "actual_data": "Cloud +63% YoY confirmed; Q1 backlog +28% QoQ",
             "thesis_impact": "Cloud growth pillar 강화 → SOTP cloud EV +12%"},
            {"question": "FY26 Capex 가이던스 유지?", "answer_status": "no",
             "actual_data": "Capex $180-190B (전년비 +20% 상향)",
             "thesis_impact": "FCF 압박 가시화 → Bear 시나리오 가중치 상승"},
        ],
        "thesis_impact": thesis_impact,
        "light_verdict_update": light_verdict,
        "post_print_action": {
            "recommendation": "Hold",
            "rationale": (
                "Beat은 옵션 시장에 이미 반영됨 (+6.5%). Cloud 모멘텀 강화는 thesis 강화이지만 "
                "entry 매력도 낮음. Mode C 재실행으로 DCF 재계산 후 의사결정 권고."
            ),
            "entry_levels": [
                {"price": 395.00, "trigger": "Post-pop pullback to 5d MA", "size": "1/3 add"},
                {"price": 380.00, "trigger": "Pre-print level 회복", "size": "Full add"},
            ],
            "exit_levels": [
                {"price": 440.00, "trigger": "Bull target 근접", "action": "Trim 1/3"},
                {"price": 360.00, "trigger": "Cloud growth 둔화 초기 신호", "action": "Reassess"},
            ],
        },
        "report_path": "output/reports/GOOGL_E_review_ko_2026-04-30.html",
    }


class RenderEarningsReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render = load_render_module()

    def test_hero_contains_ticker_d_plus_badge_beat_and_stock_reaction(self) -> None:
        """Test 1: Hero contains ticker + D+N badge + beat/miss + stock reaction."""
        analysis = make_review_analysis(beat=True)
        html = self.render.build_review_html(analysis)
        self.assertIn("GOOGL", html, "ticker missing")
        self.assertIn("D+1", html, "D+N window badge missing")
        self.assertIn("BEAT", html, "BEAT label missing in hero")
        # Stock reaction (next-day +6.5%)
        self.assertIn("6.5", html, "next-day stock reaction missing in hero")

    def test_all_six_sections_rendered_with_full_data(self) -> None:
        """Test 2: All 6 sections rendered when full data present."""
        analysis = make_review_analysis()
        html = self.render.build_review_html(analysis)
        for section_id in [
            "section-print-snapshot",
            "section-guidance",
            "section-questions-answered",
            "section-thesis-impact",
            "section-light-verdict",
            "section-post-print",
        ]:
            self.assertIn(
                section_id, html,
                f"section id `{section_id}` missing from rendered HTML",
            )

    def test_beat_miss_color_coding(self) -> None:
        """Test 3: Beat/miss color coding (green for beat, red for miss)."""
        # Beat case: green emerald gradient + green badge classes
        beat_html = self.render.build_review_html(make_review_analysis(beat=True))
        self.assertIn("#10b981", beat_html, "emerald hero gradient missing for beat")
        self.assertIn("text-green", beat_html, "green text class missing for beat")

        # Miss case: rose-orange gradient + red text class
        miss_html = self.render.build_review_html(make_review_analysis(beat=False))
        # Either #f97316 (orange terminus) or #b91c1c (rose) appears
        self.assertTrue(
            "#f97316" in miss_html or "#b91c1c" in miss_html,
            "rose-orange hero gradient missing for miss",
        )
        self.assertIn("text-red", miss_html, "red text class missing for miss")
        # MISS label shown
        self.assertIn("MISS", miss_html, "MISS label missing in hero")

    def test_outdated_flag_applies_badge_outdated_class(self) -> None:
        """Test 4: OD-F3 — light_verdict_update.outdated_flag=true shows badge-outdated."""
        analysis = make_review_analysis(outdated=True)
        html = self.render.build_review_html(analysis)
        # The outdated badge styling must appear
        self.assertIn("badge-outdated", html, "badge-outdated class missing")
        self.assertIn("DCF 미재실행", html, "outdated caption missing")

    def test_mode_c_rerun_banner_renders_when_recommended(self) -> None:
        """Test 5: OD-F3 — mode_c_rerun_recommended=true shows rerun banner."""
        analysis = make_review_analysis(rerun_recommended=True)
        html = self.render.build_review_html(analysis)
        self.assertIn("Mode C 재실행 권고", html,
                      "Mode C rerun banner missing when recommended")
        self.assertIn("D+2 ~ D+5", html, "rerun window missing")
        # Banner must come before footer
        banner_idx = html.find("Mode C 재실행 권고")
        footer_idx = html.find("<footer")
        self.assertGreater(banner_idx, 0)
        self.assertGreater(footer_idx, banner_idx,
                           "rerun banner must be positioned before <footer>")

        # Negative case: when not recommended, banner is not in output
        analysis_no_rerun = make_review_analysis(rerun_recommended=False)
        html_no = self.render.build_review_html(analysis_no_rerun)
        self.assertNotIn("Mode C 재실행 권고", html_no,
                         "rerun banner must NOT render when mode_c_rerun_recommended=false")

    def test_no_prior_mode_c_backward_compat(self) -> None:
        """Test 6: Backward compat — Review without prior Mode C → graceful stubs."""
        analysis = make_review_analysis(has_prior_mode_c=False)
        html = self.render.build_review_html(analysis)
        # Thesis Impact stub
        self.assertIn("No prior Mode C baseline", html,
                      "first-look review note missing for no-prior case")
        # Light Verdict no-prior stub
        self.assertIn("Mode C 재실행으로 R/R 산출 권고", html,
                      "light verdict no-prior stub missing")

    def test_korean_output_disclaimer_and_source_tags(self) -> None:
        """Test 7: Korean output, disclaimer, source tags."""
        analysis = make_review_analysis(language="ko")
        html = self.render.build_review_html(analysis)
        # Korean section titles
        self.assertIn("Print Snapshot", html)
        self.assertIn("가이던스 업데이트", html)
        self.assertIn("핵심 질문 답변", html)
        # Disclaimer present
        self.assertIn("Disclaimer", html)
        self.assertIn("not investment advice", html.lower())
        # Source tags
        for tag in ["[Company]", "[Est]", "[Portal]"]:
            self.assertIn(tag, html, f"source tag {tag} missing")
        # Korean font
        self.assertIn("Noto+Sans+KR", html)

    def test_stock_reaction_missing_renders_dashes(self) -> None:
        """Test 8: Stock reaction missing → graceful em-dash handling."""
        analysis = make_review_analysis(has_stock_reaction=False)
        html = self.render.build_review_html(analysis)
        # Should not crash; em-dashes appear in hero post-market/next-day cells
        # The hero section is rendered even when reaction is missing
        self.assertIn("Post-market", html)
        self.assertIn("Next-day", html)
        # Em-dash for missing reaction values
        self.assertIn("—", html)

    def test_dispatch_renders_review_path(self) -> None:
        """Dispatch sanity — render_earnings routes review correctly."""
        analysis = make_review_analysis()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "GOOGL_E_review_ko_2026-04-30.html"
            written = self.render.render_earnings(analysis, output_path=str(out_path))
            self.assertEqual(Path(written), out_path)
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("EARNINGS REVIEW", content)

    def test_invalid_sub_mode_raises(self) -> None:
        """Dispatch error case: missing/invalid earnings_sub_mode raises ValueError."""
        analysis = make_review_analysis()
        analysis["earnings_sub_mode"] = "invalid"
        with self.assertRaises(ValueError):
            self.render.render_earnings(analysis, output_path="/tmp/should_not_be_written.html")


if __name__ == "__main__":
    unittest.main()
