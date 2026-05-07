"""Mode E v2 accessibility-layer renderer tests.

Verifies that `render-earnings.py` correctly surfaces the four v2
accessibility blocks when present (TL;DR, segment breakdown, beginner
notes, glossary) and gracefully omits each block when absent. The
backward-compatibility behaviour matters: legacy v1 Mode E snapshots
written before the accessibility layer existed should still render
without raising.
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


def make_review_minimum() -> dict[str, Any]:
    """Bare-minimum Review fixture, no accessibility layer."""
    return {
        "ticker": "AMD",
        "company_name": "Advanced Micro Devices",
        "currency": "USD",
        "data_mode": "standard",
        "output_mode": "E",
        "earnings_sub_mode": "review",
        "earnings_window": {
            "actual_earnings_date": "2026-05-05",
            "days_since": 1,
            "window_label": "D+1",
        },
        "output_language": "ko",
        "analysis_date": "2026-05-07",
        "price_at_analysis": 421.39,
        "actual_vs_consensus": {
            "eps": {"actual": 1.37, "consensus": 1.30, "surprise_pct": 5.4,
                    "beat": True, "tag": "[Company]"},
            "revenue": {"actual": 10250, "consensus": 10100, "surprise_pct": 1.5,
                        "beat": True, "unit": "millions_usd", "tag": "[Company]"},
            "segments": [],
        },
        "stock_reaction": {"post_market_pct": 7.5, "next_day_pct": 18.6,
                           "tag": "[Portal]"},
        "guidance_delta": {
            "fy_eps_consensus_pre": 5.20,
            "fy_eps_consensus_post": 5.55,
            "delta_pct": 6.7,
            "tone": "raised",
            "tag": "[Est]",
        },
        "key_questions_answered": [],
        "thesis_impact": {"long_pillars": [], "short_pillars": []},
        "light_verdict_update": {
            "prior_rr_score": 1.40, "updated_rr_score": None,
            "prior_verdict": "관찰", "updated_verdict": "관찰",
            "reason": "Forward EPS 컨센서스 상향. DCF 미재실행.",
            "outdated_flag": True, "mode_c_rerun_recommended": True,
            "rerun_window": "D+2 ~ D+5",
        },
        "post_print_action": {
            "recommendation": "Hold",
            "rationale": "Beat 기 반영. Mode C 재실행 권고.",
            "entry_levels": [], "exit_levels": [],
        },
    }


def add_accessibility_layer(analysis: dict[str, Any]) -> dict[str, Any]:
    """Attach the v2 accessibility layer to a Review fixture."""
    analysis = dict(analysis)
    analysis["tldr_review"] = {
        "bullets": [
            "EPS $1.37 / 매출 $10.25B 양쪽 비트 — Data Center +57% YoY [Company]",
            "Q2 가이던스 $11.2B vs 컨센 $10.5B — +6.7% 상회 [Est]",
            "주가 D+1 +18.6% 폭등 — 비트 기 반영, 추격 비추천 [Portal]",
        ],
        "tone": "positive",
    }
    analysis["segment_breakdown"] = {
        "tag": "[Company]",
        "sources": ["AMD Q1 2026 press release"],
        "segments": [
            {"name": "Data Center", "revenue_b": 5.8, "yoy_growth_pct": 57,
             "share_of_revenue_pct": 56.6, "operating_margin_pct": 28,
             "highlights": "EPYC 서버 CPU + Instinct MI300 GPU 동시 ramp."},
            {"name": "Client", "revenue_b": 2.885, "yoy_growth_pct": 26,
             "share_of_revenue_pct": 28.1, "operating_margin_pct": None,
             "highlights": "Ryzen PC CPU 점유율 확대."},
            {"name": "Gaming", "revenue_b": 0.72, "yoy_growth_pct": 11,
             "share_of_revenue_pct": 7.0, "operating_margin_pct": None,
             "highlights": "Radeon GPU 수요가 콘솔 약세를 부분 상쇄."},
            {"name": "Embedded", "revenue_b": 0.873, "yoy_growth_pct": 6,
             "share_of_revenue_pct": 8.5, "operating_margin_pct": None,
             "highlights": "Xilinx 인수 후 산업/통신 인프라 수요 정상화."},
        ],
        "concentration_note": "Data Center + Client 합산 84.7%.",
    }
    analysis["beginner_notes"] = {
        "print_snapshot": (
            "이번 분기 EPS는 컨센서스 대비 +5.4%, 매출은 +1.5% 상회했다. "
            "헤드라인 비트보다 더 중요한 것은 Data Center +57% YoY 폭증이다. "
            "AI 인프라 수요가 직접 반영된 결과다."
        ),
        "guidance": (
            "Q2 가이던스 $11.2B는 컨센서스 $10.5B 대비 +6.7% 상회로 강한 신호다. "
            "회사가 향후 분기에 대한 자신감을 명시적으로 표현했다는 뜻이다. "
            "GM 56% 가이던스도 동시 발표로 마진 확장 모멘텀이 확인됐다."
        ),
    }
    analysis["glossary"] = [
        {"term": "Surprise %",
         "def": "실제 실적이 컨센서스에서 벗어난 정도. ±2% 이내 정상, ±5% 이상이면 big surprise로 분류된다."},
        {"term": "Data Center",
         "def": "기업·하이퍼스케일러용 서버에 들어가는 CPU/GPU 매출. AMD에서는 EPYC + Instinct 합산이다."},
        {"term": "Forward P/E",
         "def": "현재 주가를 향후 12개월 예상 EPS로 나눈 값. 회사의 미래 이익 대비 가격이 비싼지 가늠하는 지표다."},
        {"term": "Multiple Re-rating",
         "def": "회사의 fundamentals에 큰 변화가 없어도 시장이 부여하는 P/E 배수 자체가 바뀌는 현상이다."},
        {"term": "Capex",
         "def": "Capital Expenditure — 회사가 미래 매출을 위해 설비/R&D 인프라에 투입하는 자본적 지출이다."},
    ]
    return analysis


class RenderEarningsAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render = load_render_module()

    def test_tldr_section_renders_with_three_bullets(self) -> None:
        """TL;DR section renders with all 3 bullets when tldr_review provided."""
        analysis = add_accessibility_layer(make_review_minimum())
        html = self.render.build_review_html(analysis)
        self.assertIn("section-tldr", html, "TL;DR section id missing")
        self.assertIn("TL;DR", html, "TL;DR label missing")
        for bullet in analysis["tldr_review"]["bullets"]:
            # Each bullet's leading text must appear (we drop trailing source tag
            # for the substring check, the renderer escapes the rest verbatim).
            head = bullet.split(" — ")[0][:30]
            self.assertIn(head, html, f"TL;DR bullet missing: {head!r}")

    def test_segment_table_renders_when_breakdown_provided(self) -> None:
        """Segment breakdown table renders all segments when segment_breakdown provided."""
        analysis = add_accessibility_layer(make_review_minimum())
        html = self.render.build_review_html(analysis)
        self.assertIn("사업부별 매출 분해", html, "segment table heading missing")
        for seg in analysis["segment_breakdown"]["segments"]:
            self.assertIn(seg["name"], html, f"segment {seg['name']!r} missing")
        self.assertIn("Data Center", html)
        self.assertIn("EPYC", html)

    def test_glossary_footer_renders_with_all_entries(self) -> None:
        """Glossary footer renders all entries when glossary provided."""
        analysis = add_accessibility_layer(make_review_minimum())
        html = self.render.build_review_html(analysis)
        self.assertIn("section-glossary", html, "glossary section id missing")
        self.assertIn("용어 풀이", html, "glossary heading missing")
        for entry in analysis["glossary"]:
            self.assertIn(entry["term"], html, f"glossary term {entry['term']!r} missing")

    def test_beginner_notes_appear_in_relevant_sections(self) -> None:
        """Beginner notes render when beginner_notes provided."""
        analysis = add_accessibility_layer(make_review_minimum())
        html = self.render.build_review_html(analysis)
        # The renderer surfaces beginner notes via the _beginner_note() helper
        # alongside print_snapshot and guidance sections.
        self.assertIn("일반 투자자 입장에서", html,
                      "beginner-friendly callout label missing")
        # First sentence of print_snapshot note is escaped into HTML
        head = analysis["beginner_notes"]["print_snapshot"][:30]
        self.assertIn(head, html, "print_snapshot beginner note text missing")
        head_g = analysis["beginner_notes"]["guidance"][:30]
        self.assertIn(head_g, html, "guidance beginner note text missing")

    def test_backward_compat_legacy_v1_renders_without_accessibility(self) -> None:
        """Legacy v1 Mode E snapshot (no accessibility layer) still renders."""
        analysis = make_review_minimum()
        html = self.render.build_review_html(analysis)
        # The hero / sections still render
        self.assertIn("AMD", html, "ticker missing on legacy render")
        self.assertIn("D+1", html, "window badge missing on legacy render")
        # Accessibility blocks must be absent (no crash, no empty placeholder)
        self.assertNotIn("section-tldr", html,
                         "TL;DR section unexpectedly rendered for legacy snapshot")
        self.assertNotIn("section-glossary", html,
                         "Glossary section unexpectedly rendered for legacy snapshot")
        self.assertNotIn("사업부별 매출 분해", html,
                         "Segment breakdown unexpectedly rendered for legacy snapshot")
        self.assertNotIn("일반 투자자 입장에서", html,
                         "Beginner-note callout unexpectedly rendered for legacy snapshot")

    def test_partial_accessibility_layer_renders_only_provided_blocks(self) -> None:
        """Partial accessibility layer (TL;DR only) renders only that block."""
        analysis = make_review_minimum()
        analysis["tldr_review"] = {
            "bullets": ["AAA", "BBB", "CCC"],
            "tone": "mixed",
        }
        html = self.render.build_review_html(analysis)
        self.assertIn("section-tldr", html, "TL;DR section missing when provided")
        self.assertNotIn("section-glossary", html,
                         "Glossary section unexpectedly rendered without glossary data")
        self.assertNotIn("사업부별 매출 분해", html,
                         "Segment breakdown unexpectedly rendered without segment_breakdown")


if __name__ == "__main__":
    unittest.main()
