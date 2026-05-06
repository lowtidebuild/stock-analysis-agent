"""Phase C — Mode B Macro Context (Light) tests.

Verifies:
1. Mode B `analysis-result.json` carrying a `macro_context_light` block renders
   key macro series + per-peer narrative paragraphs in the HTML output.
2. Backward compatibility — analyses without `macro_context_light` render
   without errors and without leaving an empty section behind.
3. Edge case — single-peer fixtures still render without crashes (the macro
   section is allowed to render at most one narrative card).
4. Series count invariant — light bundle holds 3-5 series (no full Mode C
   sensitivity table).
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
    / "render-comparison.py"
)


def load_render_module():
    spec = importlib.util.spec_from_file_location("render_comparison", RENDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_comparison"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_peer(ticker: str, company_name: str, *, rr_score: float = 1.5) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "analysis": {
            "ticker": ticker,
            "company_name": company_name,
            "currency": "KRW",
            "market": "KR",
            "output_mode": "B",
            "output_language": "ko",
            "price_at_analysis": 70000,
            "rr_score": rr_score,
            "verdict": "관찰",
            "scenarios": {
                "bull": {"target": 90000, "return_pct": 28, "probability": 0.30, "key_assumption": "메모리 사이클 강세"},
                "base": {"target": 78000, "return_pct": 11, "probability": 0.45, "key_assumption": "사이클 정상"},
                "bear": {"target": 55000, "return_pct": -22, "probability": 0.25, "key_assumption": "수요 둔화"},
            },
            "top_risks": [],
            "upcoming_catalysts": [],
        },
        "validated_metrics": {},
    }


def macro_block_two_peers() -> dict[str, Any]:
    return {
        "key_series": [
            {"id": "DGS10", "label": "10Y Treasury", "value": 4.45, "unit": "%", "tag": "[Macro]"},
            {"id": "USD_KRW", "label": "USD/KRW", "value": 1380, "unit": "KRW", "tag": "[Macro]"},
            {"id": "Memory_ASP_index", "label": "Memory ASP", "value": "Strong", "tag": "[News]"},
        ],
        "narrative_per_peer": {
            "005930": (
                "삼성전자는 메모리 + 모바일 + VD 다각화로 USD/KRW 강세 시 환차익 부분 상쇄. "
                "Beta 1.3은 매크로 둔화 시 SK 대비 상대적으로 안정."
            ),
            "000660": (
                "SK하이닉스는 메모리 단일 베팅으로 메모리 ASP 사이클에 100% 노출. "
                "Beta 2.0은 금리 +50bp 시 -10~15% 추가 하락 risk."
            ),
        },
    }


class RenderMacroContextLightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render = load_render_module()

    def test_macro_section_renders_all_key_series_and_narratives(self) -> None:
        """Test 1: fixture with macro_context_light + 2 peers renders fully."""
        peers = [
            make_peer("005930", "삼성전자", rr_score=1.6),
            make_peer("000660", "SK하이닉스", rr_score=1.9),
        ]
        macro = macro_block_two_peers()
        html = self.render.render_macro_context_light(peers, macro, korean=True)

        # Each key series label must appear
        for series in macro["key_series"]:
            self.assertIn(
                series["label"],
                html,
                f"macro section must render key series label: {series['label']}",
            )

        # Per-peer narrative text must appear
        for ticker, narrative in macro["narrative_per_peer"].items():
            # Use a substring (Korean rendering may add wrapping markup)
            snippet = narrative.split(".")[0]
            self.assertIn(
                snippet,
                html,
                f"macro section must render narrative for {ticker}: {snippet}",
            )

        # Each peer ticker must appear in the section
        for peer in peers:
            self.assertIn(peer["ticker"], html)

        # Section heading present (Korean)
        self.assertIn("매크로", html)

    def test_macro_section_returns_empty_when_no_payload(self) -> None:
        """Test 2: backward compat — missing `macro_context_light` → empty string."""
        peers = [
            make_peer("005930", "삼성전자"),
            make_peer("000660", "SK하이닉스"),
        ]
        # Pass None payload (analyst did not produce macro_context_light)
        html = self.render.render_macro_context_light(peers, None, korean=True)
        self.assertEqual(html.strip(), "", "missing macro_context_light → empty render")

        # Also empty payload object
        html_empty = self.render.render_macro_context_light(peers, {}, korean=True)
        self.assertEqual(html_empty.strip(), "")

    def test_macro_section_handles_single_peer_edge(self) -> None:
        """Test 3: 1 peer → renders without crashing."""
        peers = [make_peer("AAPL", "Apple Inc.")]
        macro = {
            "key_series": [
                {"id": "DGS10", "label": "10Y Treasury", "value": 4.45, "unit": "%", "tag": "[Macro]"},
                {"id": "DTWEXBGS", "label": "USD Index", "value": 102.3, "tag": "[Macro]"},
                {"id": "UMCSENT", "label": "Consumer Sentiment", "value": 71.8, "tag": "[Macro]"},
            ],
            "narrative_per_peer": {
                "AAPL": "AAPL은 글로벌 수요 노출이 큰 하드웨어 + 서비스 혼합. USD 강세는 해외 매출 환산에 부정적.",
            },
        }
        html = self.render.render_macro_context_light(peers, macro, korean=True)
        # Must not crash, must include the AAPL ticker
        self.assertIn("AAPL", html)
        self.assertIn("10Y Treasury", html)

    def test_macro_section_series_count_within_bounds(self) -> None:
        """Test 4: light bundle requires 3-5 series."""
        peers = [
            make_peer("005930", "삼성전자"),
            make_peer("000660", "SK하이닉스"),
        ]
        macro = macro_block_two_peers()
        # Schema must hold 3-5 series
        n = len(macro["key_series"])
        self.assertGreaterEqual(n, 3, "light bundle must have at least 3 series")
        self.assertLessEqual(n, 5, "light bundle is capped at 5 series (no Mode C table)")

        # And the renderer must surface exactly that many series labels
        html = self.render.render_macro_context_light(peers, macro, korean=True)
        for series in macro["key_series"]:
            self.assertIn(series["label"], html)

    def test_render_html_integration_includes_macro_section(self) -> None:
        """Integration: macro_context_light at top-level main_analysis renders inside render_html."""
        peers = [
            make_peer("005930", "삼성전자", rr_score=1.6),
            make_peer("000660", "SK하이닉스", rr_score=1.9),
        ]
        main_analysis = {
            "ticker": "005930",
            "peer_tickers": ["000660"],
            "output_mode": "B",
            "output_language": "ko",
            "analysis_date": "2026-05-07",
            "macro_context_light": macro_block_two_peers(),
        }
        html = self.render.render_html(peers, main_analysis)
        # Main heading + a macro key series must be present
        self.assertIn("매크로", html)
        self.assertIn("USD/KRW", html)
        self.assertIn("삼성전자는 메모리", html)
        self.assertIn("SK하이닉스는 메모리", html)

    def test_render_html_without_macro_field_renders_cleanly(self) -> None:
        """Integration backward compat: no macro field in main analysis → no broken section."""
        peers = [
            make_peer("005930", "삼성전자"),
            make_peer("000660", "SK하이닉스"),
        ]
        main_analysis = {
            "ticker": "005930",
            "peer_tickers": ["000660"],
            "output_mode": "B",
            "output_language": "ko",
            "analysis_date": "2026-05-07",
        }
        html = self.render.render_html(peers, main_analysis)
        # Pipeline still produces a valid HTML doc
        self.assertIn("<html", html)
        self.assertIn("</html>", html)
        # No empty macro heading dangling (the macro h2 only appears when payload exists)
        self.assertNotIn("매크로 컨텍스트 · 종목별 노출 차이", html)


if __name__ == "__main__":
    unittest.main()
