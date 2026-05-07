"""Phase E — Mode C Catalyst Timeline contract + aggregator tests.

These tests verify the contract pieces that together make the Mode C
"upcoming catalysts" section render as a Gantt-style timeline grouped by
category (earnings/regulatory/product/macro/other), backed by the
extended ``upcoming_catalysts[]`` schema and the optional
peer-mini-pipeline merge.

Per ADR 0001 the user-facing HTML for Mode C is populated manually from
``.claude/skills/dashboard-generator/references/html-template.md``; the
template + framework spec + analyst AGENT instructions are therefore the
canonical contract surfaces.

Scope:

1. Framework spec mentions the catalyst timeline + the 5 categories.
2. HTML template carries the ``{CATALYST_TIMELINE}`` placeholder placed
   in a sensible location (in/after the Strategy / What-Would-Make-Me-Wrong
   section since that's where Upcoming Catalysts already live in
   ``analysis-framework-dashboard.md``).
3. Analyst AGENT.md documents the new ``start_date`` / ``end_date`` /
   ``category`` / ``ticker`` fields and the legacy fallback rule.
4. ``catalyst-aggregator.py`` exposes a ``normalize_catalyst_for_timeline``
   helper that:
   - Maps legacy ``date`` → ``start_date == end_date``.
   - Defaults missing ``category`` to ``"other"``.
   - Handles ISO date ranges where ``start_date != end_date``.
   - Defaults missing ``ticker`` to a passed-in subject ticker.
5. ``build_timeline_payload`` merges subject + peer catalysts, attaches
   ticker labels, and is ordered by ``start_date``.
6. Significance is preserved (``high``/``medium``/``low``) so the renderer
   can size markers accordingly.
7. Empty input → empty timeline payload (no crash, renderer can hide
   the section).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FRAMEWORK_PATH = REPO_ROOT / "references" / "analysis-framework-dashboard.md"
TEMPLATE_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "dashboard-generator"
    / "references"
    / "html-template.md"
)
ANALYST_AGENT_PATH = REPO_ROOT / ".claude" / "agents" / "analyst" / "AGENT.md"
CATALYST_PATH = (
    REPO_ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "catalyst-aggregator.py"
)


def _load_catalyst_module():
    spec = importlib.util.spec_from_file_location("catalyst_aggregator_phasee", CATALYST_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class CatalystTimelineFrameworkContractTests(unittest.TestCase):
    """Contract surface: spec docs + template placeholder + agent instructions."""

    def test_framework_documents_catalyst_timeline(self) -> None:
        text = FRAMEWORK_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "Catalyst Timeline" in text or "카탈리스트 타임라인" in text or "catalyst_timeline" in text,
            "analysis-framework-dashboard.md must document the Mode C "
            "Catalyst Timeline section so analysts know to populate it.",
        )

    def test_framework_documents_five_categories(self) -> None:
        text = FRAMEWORK_PATH.read_text(encoding="utf-8")
        for cat in ("earnings", "regulatory", "product", "macro", "other"):
            self.assertIn(
                cat,
                text,
                f"framework must list the '{cat}' category for the catalyst timeline.",
            )

    def test_template_has_catalyst_timeline_placeholder(self) -> None:
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "{CATALYST_TIMELINE}",
            text,
            "html-template.md must expose a {CATALYST_TIMELINE} placeholder so "
            "the manual-population renderer can inject the Gantt-style "
            "catalyst timeline section.",
        )

    def test_template_mentions_category_color_codes(self) -> None:
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        # The example markup must mention each category as a Tailwind color
        # so the populator knows the color convention.
        for cat in ("earnings", "regulatory", "product", "macro", "other"):
            self.assertIn(
                cat,
                text,
                f"template must document the '{cat}' category badge / color.",
            )

    def test_analyst_agent_documents_new_catalyst_schema(self) -> None:
        text = ANALYST_AGENT_PATH.read_text(encoding="utf-8")
        for field in ("start_date", "end_date", "category"):
            self.assertIn(
                field,
                text,
                f"analyst/AGENT.md must instruct analysts to populate "
                f"'{field}' on upcoming_catalysts[] (with legacy fallback).",
            )


class CatalystAggregatorTimelineHelpersTests(unittest.TestCase):
    """Aggregator-side contract: normalize + merge helpers used by Mode C."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalyst = _load_catalyst_module()

    def test_normalize_legacy_date_field_to_range(self) -> None:
        normalize = self.catalyst.normalize_catalyst_for_timeline
        rec = normalize(
            {
                "date": "2026-07-29",
                "event_type": "earnings",
                "description": "Q2 2026 실적 발표",
                "significance": "high",
            },
            subject_ticker="GOOGL",
        )
        self.assertEqual(rec["start_date"], "2026-07-29")
        self.assertEqual(rec["end_date"], "2026-07-29")
        # Legacy entries with an "earnings" event_type should map to the
        # earnings category even when the caller didn't set one explicitly.
        self.assertEqual(rec["category"], "earnings")
        self.assertEqual(rec["ticker"], "GOOGL")
        self.assertEqual(rec["significance"], "high")

    def test_normalize_defaults_category_to_other_when_unknown(self) -> None:
        normalize = self.catalyst.normalize_catalyst_for_timeline
        rec = normalize(
            {
                "date": "2026-09-01",
                "description": "잡다한 IR 일정 (분류 불가)",
            },
            subject_ticker="GOOGL",
        )
        self.assertEqual(rec["start_date"], "2026-09-01")
        self.assertEqual(rec["end_date"], "2026-09-01")
        # No keyword match and no event_type → category falls back to "other".
        self.assertEqual(rec["category"], "other")
        self.assertEqual(rec["ticker"], "GOOGL")

    def test_normalize_preserves_explicit_range(self) -> None:
        normalize = self.catalyst.normalize_catalyst_for_timeline
        rec = normalize(
            {
                "start_date": "2026-10-01",
                "end_date": "2026-12-15",
                "category": "regulatory",
                "ticker": "GOOGL",
                "description": "DC Circuit appeal hearings window",
                "significance": "high",
            },
            subject_ticker="GOOGL",
        )
        self.assertEqual(rec["start_date"], "2026-10-01")
        self.assertEqual(rec["end_date"], "2026-12-15")
        self.assertEqual(rec["category"], "regulatory")
        self.assertEqual(rec["ticker"], "GOOGL")
        # Range catalysts should be flagged so the renderer can draw a bar
        # rather than a point.
        self.assertTrue(rec["is_range"])

    def test_normalize_explicit_category_wins_over_inference(self) -> None:
        normalize = self.catalyst.normalize_catalyst_for_timeline
        rec = normalize(
            {
                "date": "2026-08-15",
                "event_type": "earnings",  # would otherwise infer earnings
                "category": "macro",  # caller explicitly overrides
                "description": "FOMC + earnings overlap (analyst override)",
                "significance": "medium",
            },
            subject_ticker="GOOGL",
        )
        self.assertEqual(rec["category"], "macro")

    def test_normalize_handles_significance_values(self) -> None:
        normalize = self.catalyst.normalize_catalyst_for_timeline
        for sig in ("high", "medium", "low"):
            rec = normalize(
                {
                    "date": "2026-08-15",
                    "category": "product",
                    "description": "Test",
                    "significance": sig,
                },
                subject_ticker="GOOGL",
            )
            self.assertEqual(rec["significance"], sig)
        # Missing significance → default medium so the renderer can size the
        # marker without crashing.
        rec_default = normalize(
            {
                "date": "2026-08-15",
                "category": "product",
                "description": "Test",
            },
            subject_ticker="GOOGL",
        )
        self.assertEqual(rec_default["significance"], "medium")


class CatalystAggregatorTimelinePayloadTests(unittest.TestCase):
    """Building the timeline payload (subject + optional peers)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalyst = _load_catalyst_module()

    def test_build_timeline_payload_for_subject_only(self) -> None:
        build = self.catalyst.build_timeline_payload
        subject_catalysts = [
            {
                "date": "2026-07-29",
                "event_type": "earnings",
                "description": "Q2 2026 실적 발표",
                "significance": "high",
            },
            {
                "date": "2026-10-28",
                "event_type": "earnings",
                "description": "Q3 2026 실적",
                "significance": "high",
            },
            {
                "start_date": "2026-10-01",
                "end_date": "2026-12-15",
                "category": "regulatory",
                "description": "DC Circuit DOJ antitrust appeal",
                "significance": "high",
            },
            {
                "date": "2026-09-15",
                "category": "product",
                "description": "Gemini 3.0 launch (estimated)",
                "significance": "medium",
            },
            {
                "date": "2026-12-12",
                "category": "macro",
                "description": "FOMC December decision",
                "significance": "low",
            },
        ]
        payload = build(
            subject_ticker="GOOGL",
            subject_catalysts=subject_catalysts,
        )
        # Five distinct items, ordered by start_date ascending.
        self.assertEqual(len(payload["events"]), 5)
        starts = [e["start_date"] for e in payload["events"]]
        self.assertEqual(starts, sorted(starts))
        # All carry GOOGL ticker (subject default).
        self.assertTrue(all(e["ticker"] == "GOOGL" for e in payload["events"]))
        # Categories cover 4 distinct buckets present in the input.
        seen_cats = {e["category"] for e in payload["events"]}
        self.assertEqual(
            seen_cats,
            {"earnings", "regulatory", "product", "macro"},
        )
        # Range catalyst is marked accordingly.
        regulatory = next(e for e in payload["events"] if e["category"] == "regulatory")
        self.assertTrue(regulatory["is_range"])
        # Subject ticker is recorded on the payload itself.
        self.assertEqual(payload["subject_ticker"], "GOOGL")
        # Peer count = 0 when no peer data passed.
        self.assertEqual(payload["peer_count"], 0)

    def test_build_timeline_payload_merges_peer_catalysts(self) -> None:
        build = self.catalyst.build_timeline_payload
        subject_catalysts = [
            {
                "date": "2026-07-29",
                "event_type": "earnings",
                "description": "Q2 2026 실적 발표",
                "significance": "high",
            },
        ]
        # Phase D peer mini-pipeline outputs surface a `next_earnings_date`
        # on each peer JSON; the aggregator should accept that as input.
        peer_catalysts = {
            "MSFT": [
                {
                    "date": "2026-07-30",
                    "event_type": "earnings",
                    "description": "MSFT Q4 FY26 earnings",
                    "significance": "high",
                }
            ],
            "META": [
                {
                    "date": "2026-07-31",
                    "event_type": "earnings",
                    "description": "META Q2 2026 earnings",
                    "significance": "high",
                }
            ],
        }
        payload = build(
            subject_ticker="GOOGL",
            subject_catalysts=subject_catalysts,
            peer_catalysts=peer_catalysts,
        )
        # 1 subject + 2 peer catalysts.
        self.assertEqual(len(payload["events"]), 3)
        tickers = {e["ticker"] for e in payload["events"]}
        self.assertEqual(tickers, {"GOOGL", "MSFT", "META"})
        # Peer count = 2.
        self.assertEqual(payload["peer_count"], 2)
        # Subject row is flagged so the renderer can emphasize it.
        subject_event = next(e for e in payload["events"] if e["ticker"] == "GOOGL")
        self.assertTrue(subject_event["is_subject"])
        peer_event = next(e for e in payload["events"] if e["ticker"] == "MSFT")
        self.assertFalse(peer_event["is_subject"])

    def test_build_timeline_payload_empty_inputs(self) -> None:
        build = self.catalyst.build_timeline_payload
        payload = build(subject_ticker="GOOGL", subject_catalysts=[])
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["subject_ticker"], "GOOGL")
        self.assertEqual(payload["peer_count"], 0)
        # Renderer can detect emptiness via `events == []` and hide the
        # section without crashing.

    def test_build_timeline_payload_excludes_invalid_dates(self) -> None:
        """Catalysts with no parseable date should be skipped, not crash."""
        build = self.catalyst.build_timeline_payload
        subject_catalysts = [
            {
                "date": "2026-07-29",
                "event_type": "earnings",
                "description": "Valid",
                "significance": "high",
            },
            {
                # Garbage date — must not blow up the timeline build.
                "date": "TBD",
                "description": "Unscheduled item",
            },
            {
                "date": None,
                "description": "Missing date",
            },
        ]
        payload = build(subject_ticker="GOOGL", subject_catalysts=subject_catalysts)
        # Only the valid catalyst makes it through.
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["start_date"], "2026-07-29")


class GooglFixtureRoundtripTest(unittest.TestCase):
    """Sanity check: real GOOGL catalysts (legacy schema) flow through."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalyst = _load_catalyst_module()

    def test_legacy_googl_catalysts_normalize_without_loss(self) -> None:
        legacy = [
            {
                "date": "2026-07-29 (estimated)",
                "event_type": "earnings",
                "description": "Q2 2026 실적 발표",
                "significance": "high",
                "expected_impact": "+/-5-8%",
            },
            {
                "date": "2026 Q4 / 2027 Q1",  # imprecise — should be skipped
                "event_type": "regulatory",
                "description": "DC Circuit antitrust",
                "significance": "high",
            },
        ]
        payload = self.catalyst.build_timeline_payload(
            subject_ticker="GOOGL",
            subject_catalysts=legacy,
        )
        # The well-formed earnings catalyst must survive normalization.
        # We strip the trailing parenthetical so the date parses to ISO.
        starts = [e["start_date"] for e in payload["events"]]
        self.assertIn("2026-07-29", starts)


if __name__ == "__main__":
    unittest.main()
