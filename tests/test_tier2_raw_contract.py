"""Tests for the tier2 web research extraction contract."""

from __future__ import annotations

import unittest

from tools.artifact_validation import validate_artifact_data


def _tier2_raw(**overrides) -> dict:
    payload = {
        "ticker": "AAPL",
        "collection_timestamp": "2026-04-24T00:00:00Z",
        "market": "US",
        "raw_search_results": [
            {
                "query_id": "q_market_cap_1",
                "query": "AAPL market cap",
                "rank": 1,
                "title": "Quote page",
                "url": "https://example.com/quote",
                "published_date": None,
                "retrieved_at": "2026-04-24T00:00:00Z",
                "snippet": "Market cap shown on quote page.",
                "source_domain": "example.com",
            }
        ],
        "extracted_metric_candidates": [
            {
                "candidate_id": "c_market_cap_1",
                "metric": "market_cap",
                "raw_value": "100B",
                "normalized_value": 100_000_000_000,
                "unit": "USD",
                "currency": "USD",
                "as_of_date": "2026-04-24",
                "source_url": "https://example.com/quote",
                "source_query_id": "q_market_cap_1",
                "source_result_rank": 1,
                "source_domain": "example.com",
                "extraction_method": "search_snippet",
                "confidence_candidate": "C",
                "notes": "Fixture candidate",
            }
        ],
        "metric_conflicts": [],
    }
    payload.update(overrides)
    return payload


class Tier2RawContractTests(unittest.TestCase):
    def test_valid_tier2_raw_contract_passes(self):
        self.assertEqual(validate_artifact_data("tier2-raw", _tier2_raw()), [])

    def test_requires_extracted_metric_candidates(self):
        payload = _tier2_raw()
        payload.pop("extracted_metric_candidates")

        errors = validate_artifact_data("tier2-raw", payload)

        self.assertTrue(any("extracted_metric_candidates" in error for error in errors))

    def test_rejects_legacy_data_extracted_inside_search_results(self):
        payload = _tier2_raw(
            searches_executed=[
                {
                    "query": "AAPL market cap",
                    "results": [
                        {
                            "url": "https://example.com/quote",
                            "data_extracted": {"market_cap": 100_000_000_000},
                        }
                    ],
                }
            ]
        )

        errors = validate_artifact_data("tier2-raw", payload)

        self.assertTrue(any("data_extracted" in error for error in errors))

    def test_rejects_unknown_search_snippet_reference(self):
        payload = _tier2_raw()
        payload["extracted_metric_candidates"][0]["source_query_id"] = "missing_query"

        errors = validate_artifact_data("tier2-raw", payload)

        self.assertTrue(any("source_query_id" in error and "unknown" in error for error in errors))

    def test_conflicts_preserve_multiple_candidates(self):
        payload = _tier2_raw(
            metric_conflicts=[
                {
                    "metric": "market_cap",
                    "candidates": ["c_market_cap_1"],
                    "resolution": "insufficient comparison",
                }
            ]
        )

        errors = validate_artifact_data("tier2-raw", payload)

        self.assertTrue(any("conflicts must preserve at least two candidates" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
