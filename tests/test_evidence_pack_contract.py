"""Tests for compact evidence-pack generation and validation."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.artifact_validation import validate_artifact_data, validate_artifact_file
from tools.evidence_pack import build_evidence_pack, main as evidence_pack_main
from tools.quality_report import build_raw_artifact_access_item

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_context() -> dict:
    return {
        "run_id": "run-1",
        "artifact_root": "output/runs/run-1/TEST",
        "ticker": "TEST",
    }


def _validated() -> dict:
    return {
        "ticker": "TEST",
        "market": "US",
        "data_mode": "standard",
        "requested_mode": "standard",
        "effective_mode": "standard",
        "source_profile": "yfinance_fallback",
        "source_tier": "portal_structured",
        "confidence_cap": "C",
        "validation_timestamp": "2099-01-02T03:04:05Z",
        "overall_grade": "C",
        "run_context": _run_context(),
        "validated_metrics": {
            "price_at_analysis": {
                "value": 123.45,
                "grade": "C",
                "source_type": "portal_global",
                "source_authority": "market_portal",
                "display_tag": "[Portal]",
                "tag": "[Portal]",
                "sources": ["Portal quote page"],
                "as_of_date": "2099-01-02",
            },
            "ev_ebitda": {
                "value": None,
                "grade": "D",
                "source_type": None,
                "source_authority": None,
                "display_tag": None,
                "tag": None,
                "sources": [],
                "exclusion_reason": "Not enough verified source candidates",
            },
        },
        "grade_summary": {"A": 0, "B": 0, "C": 1, "D": 1},
        "exclusions": [
            {
                "metric": "ev_ebitda",
                "reason": "Not enough verified source candidates",
                "display": "—",
            }
        ],
        "metric_conflicts": [
            {
                "metric": "price_at_analysis",
                "candidates": [{"id": "candidate_1"}, {"id": "candidate_2"}],
                "selection_reason": "Selected latest timestamp",
            }
        ],
    }


class EvidencePackContractTests(unittest.TestCase):
    def test_builder_distills_validated_metrics_without_grade_d_facts(self):
        pack = build_evidence_pack(
            _validated(),
            raw_artifact_refs=["output/runs/run-1/TEST/tier2-raw.json"],
            generated_at="2099-01-02T03:05:00Z",
        )

        self.assertEqual(pack["as_of"], "2099-01-02")
        self.assertEqual([fact["metric"] for fact in pack["facts"]], ["price_at_analysis"])
        self.assertEqual(pack["facts"][0]["grade"], "C")
        self.assertEqual(pack["exclusions"][0]["metric"], "ev_ebitda")
        self.assertEqual(pack["raw_access_policy"]["default_load"], "deny")
        self.assertNotIn("candidates", pack["conflicts"][0])
        self.assertEqual(validate_artifact_data("evidence-pack", pack), [])

    def test_validator_rejects_raw_search_payload_inside_evidence_pack(self):
        pack = build_evidence_pack(_validated(), generated_at="2099-01-02T03:05:00Z")
        pack["facts"][0]["snippet"] = "raw search text should stay out"

        errors = validate_artifact_data("evidence-pack", pack)

        self.assertTrue(any("must not embed raw fetched text" in error for error in errors))

    def test_cli_writes_valid_evidence_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            validated_path = root / "validated-data.json"
            output_path = root / "evidence-pack.json"
            validated_path.write_text(json.dumps(_validated()), encoding="utf-8")

            exit_code = evidence_pack_main(
                [
                    "--validated-data",
                    str(validated_path),
                    "--output",
                    str(output_path),
                    "--raw-artifact-ref",
                    "output/runs/run-1/TEST/tier2-raw.json",
                    "--no-infer-raw-refs",
                ]
            )

            self.assertEqual(exit_code, 0)
            result = validate_artifact_file(output_path, "evidence-pack", base_dir=ROOT)
            self.assertTrue(result["valid"])
            self.assertTrue(result["ingestion_allowed"])

    def test_analyst_default_inputs_use_evidence_pack_not_raw_artifacts(self):
        text = (ROOT / ".claude" / "agents" / "analyst" / "AGENT.md").read_text(encoding="utf-8")
        inputs_section = text.split("## Inputs (Load in This Order)", 1)[1].split("---", 1)[0]

        self.assertIn("Run-local `evidence-pack.json`", inputs_section)
        self.assertNotIn("Run-local `tier1-raw.json` (if Enhanced Mode)", inputs_section)
        self.assertNotIn("Run-local `tier2-raw.json` — for qualitative context", inputs_section)
        self.assertIn("Do not load raw artifacts by default", inputs_section)

    def test_quality_report_records_raw_artifact_access_reason(self):
        pack = build_evidence_pack(_validated(), generated_at="2099-01-02T03:05:00Z")
        analysis = {
            "raw_artifact_access": [
                {
                    "file": "output/runs/run-1/TEST/tier2-raw.json",
                    "reason": "validator_conflict_review",
                    "fields_read": ["metric_conflicts"],
                    "sanitization_present": True,
                }
            ]
        }

        item = build_raw_artifact_access_item(pack, analysis)

        self.assertEqual(item["status"], "PASS_WITH_FLAGS")
        self.assertEqual(item["raw_access_count"], 1)
        self.assertEqual(item["entries"][0]["reason"], "validator_conflict_review")

    def test_quality_report_blocks_unsanitized_raw_artifact_access(self):
        pack = build_evidence_pack(_validated(), generated_at="2099-01-02T03:05:00Z")
        analysis = {
            "raw_artifact_access": [
                {
                    "file": "output/runs/run-1/TEST/tier2-raw.json",
                    "reason": "validator_conflict_review",
                    "fields_read": ["metric_conflicts"],
                    "sanitization_present": False,
                }
            ]
        }

        item = build_raw_artifact_access_item(pack, analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "BLOCKER")
        self.assertEqual(item["blocker_action"], "terminal")


if __name__ == "__main__":
    unittest.main()
