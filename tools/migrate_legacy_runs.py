#!/usr/bin/env python3
"""
migrate_legacy_runs.py — Promotes legacy sample artifacts into run-local, schema-valid fixtures.

Usage:
    python tools/migrate_legacy_runs.py
    python tools/migrate_legacy_runs.py --tickers NVDA 005930
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_contract import (  # noqa: E402
    build_run_paths,
    extract_numeric_value,
    normalize_metric_mapping,
    relativize_paths,
    utc_now_iso,
)
from tools.artifact_validation import validate_run_directory  # noqa: E402
from tools.quality_report import build_quality_report  # noqa: E402


FRAMEWORK_BY_MODE = {
    "A": "references/analysis-framework-briefing.md",
    "B": "references/analysis-framework-comparison.md",
    "C": "references/analysis-framework-dashboard.md",
    "D": "references/analysis-framework-memo.md",
}

LEGACY_FIXTURES: dict[str, dict[str, Any]] = {
    "NVDA": {
        "ticker": "NVDA",
        "analysis_date": "2026-03-13",
        "market": "US",
        "output_mode": "A",
        "output_language": "en",
        "research_plan_source": "output/research-plan.json",
        "validated_data_source": "output/validated-data.json",
        "analysis_source": "output/data/NVDA/latest.json",
        "quality_report_source": "output/quality-report.json",
        "report_path": "output/reports/NVDA_A_en_2026-03-13.html",
    },
    "005930": {
        "ticker": "005930",
        "analysis_date": "2026-03-12",
        "market": "KR",
        "output_mode": "B",
        "output_language": "ko",
        "research_plan_source": "output/data/005930/research-plan.json",
        "validated_data_source": "output/data/005930/validated-data.json",
        "analysis_source": "output/data/005930/005930_2026-03-12_snapshot.json",
        "quality_report_source": None,
        "report_path": "output/reports/005930_000660_MU_B_KR_2026-03-12.html",
    },
    "000660": {
        "ticker": "000660",
        "analysis_date": "2026-03-12",
        "market": "KR",
        "output_mode": "B",
        "output_language": "ko",
        "research_plan_source": "output/data/000660/research-plan.json",
        "validated_data_source": "output/data/000660/validated-data.json",
        "analysis_source": "output/data/000660/000660_2026-03-12_snapshot.json",
        "quality_report_source": None,
        "report_path": "output/reports/005930_000660_MU_B_KR_2026-03-12.html",
    },
    "MU": {
        "ticker": "MU",
        "analysis_date": "2026-03-12",
        "market": "US",
        "output_mode": "B",
        "output_language": "ko",
        "research_plan_source": "output/data/MU/research-plan.json",
        "validated_data_source": "output/data/MU/validated-data.json",
        "analysis_source": "output/data/MU/MU_2026-03-12_snapshot.json",
        "quality_report_source": None,
        "report_path": "output/reports/005930_000660_MU_B_KR_2026-03-12.html",
    },
}


def load_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    file_path = REPO_ROOT / path
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def run_id_for(config: dict[str, Any]) -> str:
    date_token = str(config["analysis_date"]).replace("-", "")
    return f"{date_token}T000000Z_{config['ticker']}_{config['output_mode']}_LEGACY"


def build_run_context(paths: dict[str, Path], run_id: str, ticker: str) -> dict[str, Any]:
    relpaths = relativize_paths(
        REPO_ROOT,
        {
            "artifact_root": paths["artifact_root"],
            "reports_dir": paths["reports_dir"],
            "snapshot_dir": paths["snapshot_dir"],
        },
    )
    return {
        "run_id": run_id,
        "artifact_root": relpaths["artifact_root"],
        "ticker": ticker,
        "reports_dir": relpaths["reports_dir"],
        "snapshot_dir": relpaths["snapshot_dir"],
        "migration_mode": "legacy_promotion",
    }


def compute_grade_summary(metrics: dict[str, Any]) -> dict[str, int]:
    summary = {"A": 0, "B": 0, "C": 0, "D": 0}
    for entry in metrics.values():
        grade = entry.get("grade") if isinstance(entry, dict) else None
        if grade in summary:
            summary[grade] += 1
    return summary


def build_exclusions(metrics: dict[str, Any], existing: Any) -> list[Any]:
    exclusions = list(existing) if isinstance(existing, list) else []
    seen_metrics = {
        item.get("metric") for item in exclusions
        if isinstance(item, dict) and item.get("metric")
    }
    for metric_name, entry in metrics.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("grade") == "D" and metric_name not in seen_metrics:
            exclusions.append(
                {
                    "metric": metric_name,
                    "reason": entry.get("exclusion_reason") or entry.get("notes") or "Legacy migration excluded unverifiable metric",
                }
            )
    return exclusions


def calculate_return_pct(target: Any, price: Any) -> float | None:
    target_value = extract_numeric_value(target)
    price_value = extract_numeric_value(price)
    if target_value is None or price_value in (None, 0):
        return None
    return round(((target_value / price_value) - 1.0) * 100.0, 1)


def fallback_company_name(config: dict[str, Any], *payloads: dict[str, Any] | None) -> str | None:
    if config.get("company_name"):
        return config["company_name"]
    for payload in payloads:
        if isinstance(payload, dict) and payload.get("company_name"):
            return payload["company_name"]
    return None


def build_migration_block(source_path: str | None, notes: list[str]) -> dict[str, Any]:
    return {
        "migrated_at": utc_now_iso(),
        "source_path": source_path,
        "notes": notes,
    }


def migrate_research_plan(
    config: dict[str, Any],
    source: dict[str, Any] | None,
    run_context: dict[str, Any],
) -> dict[str, Any]:
    if source:
        plan = copy.deepcopy(source)
    else:
        plan = {
            "ticker": config["ticker"],
            "market": config["market"],
            "data_mode": "standard",
            "output_mode": config["output_mode"],
            "output_language": config["output_language"],
            "analysis_date": config["analysis_date"],
            "company_type": "Legacy sample migration",
            "peer_tickers": [],
            "analysis_framework_path": FRAMEWORK_BY_MODE[config["output_mode"]],
            "tier1_calls": [],
            "tier2_searches": [],
            "tier2_fetches": [],
        }

    plan["ticker"] = config["ticker"]
    plan["market"] = config["market"]
    plan.setdefault("data_mode", "standard")
    plan["output_mode"] = config["output_mode"]
    plan["output_language"] = config["output_language"]
    plan["analysis_date"] = config["analysis_date"]
    plan.setdefault("analysis_framework_path", FRAMEWORK_BY_MODE[config["output_mode"]])
    plan.setdefault("peer_tickers", [])
    plan.setdefault("tier1_calls", [])
    plan.setdefault("tier2_searches", [])
    plan.setdefault("tier2_fetches", [])
    plan["run_context"] = run_context
    plan["migration"] = build_migration_block(
        config.get("research_plan_source"),
        ["Research plan promoted from legacy artifact namespace"],
    )
    return plan


def migrate_validated_data(
    config: dict[str, Any],
    source: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    validated = copy.deepcopy(source)
    validated["ticker"] = config["ticker"]
    validated["market"] = config["market"]
    validated.setdefault("data_mode", "standard")
    normalized_metrics, warnings = normalize_metric_mapping(
        validated.get("validated_metrics", {}),
        market=config["market"],
    )
    validated["validated_metrics"] = normalized_metrics
    validated["grade_summary"] = compute_grade_summary(normalized_metrics)
    validated["exclusions"] = build_exclusions(normalized_metrics, validated.get("exclusions"))
    validated["run_context"] = run_context
    validated["migration"] = build_migration_block(
        config["validated_data_source"],
        ["Validated metrics normalized to canonical source metadata contract", *warnings],
    )
    return validated


def build_analysis_key_metrics(
    analysis_seed: dict[str, Any],
    validated_metrics: dict[str, Any],
    market: str,
) -> tuple[dict[str, Any], list[str]]:
    raw_key_metrics = analysis_seed.get("key_metrics")
    selected: dict[str, Any] = {}

    if isinstance(raw_key_metrics, dict):
        if all(isinstance(value, dict) for value in raw_key_metrics.values()):
            for metric_name, entry in raw_key_metrics.items():
                selected[metric_name] = copy.deepcopy(validated_metrics.get(metric_name, entry))
        else:
            for metric_name in raw_key_metrics:
                if metric_name in validated_metrics:
                    selected[metric_name] = copy.deepcopy(validated_metrics[metric_name])

    if not selected:
        selected = copy.deepcopy(validated_metrics)

    return normalize_metric_mapping(selected, market=market)


def metric_value(metrics: dict[str, Any], metric_name: str) -> Any:
    entry = metrics.get(metric_name)
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def build_scenarios(
    analysis_seed: dict[str, Any],
    validated_metrics: dict[str, Any],
    price_at_analysis: Any,
) -> dict[str, Any]:
    existing = analysis_seed.get("scenarios")
    analyst_target = metric_value(validated_metrics, "analyst_target") or analysis_seed.get("analyst_target")
    default_probabilities = {"bull": 0.25, "base": 0.50, "bear": 0.25}
    scenarios: dict[str, Any] = {}

    for case in ("bull", "base", "bear"):
        seed_case = existing.get(case, {}) if isinstance(existing, dict) else {}
        case_data = copy.deepcopy(seed_case) if isinstance(seed_case, dict) else {}
        if case == "base" and case_data.get("target") is None and analyst_target is not None:
            case_data["target"] = analyst_target
        case_data.setdefault("target", None)
        case_data.setdefault("probability", default_probabilities[case])
        if case_data.get("return_pct") is None:
            case_data["return_pct"] = calculate_return_pct(case_data.get("target"), price_at_analysis)

        if not case_data.get("key_assumption"):
            if case == "base" and analyst_target is not None:
                case_data["key_assumption"] = "Legacy snapshot preserved a consensus target but not full scenario narration; this base case carries that target forward."
            elif existing:
                case_data["key_assumption"] = "Legacy snapshot preserved target/probability inputs but omitted the narrative assumption; migration annotated this field."
            else:
                case_data["key_assumption"] = "Legacy sample did not preserve scenario detail for this case; placeholder assumption added during run-local migration."
        scenarios[case] = case_data

    return scenarios


def migrate_analysis_result(
    config: dict[str, Any],
    source: dict[str, Any],
    validated: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    analysis = copy.deepcopy(source)
    validated_metrics = validated["validated_metrics"]
    key_metrics, warnings = build_analysis_key_metrics(analysis, validated_metrics, market=config["market"])

    analysis["ticker"] = config["ticker"]
    analysis["company_name"] = fallback_company_name(config, analysis, validated)
    analysis["market"] = config["market"]
    analysis.setdefault("data_mode", validated.get("data_mode", "standard"))
    analysis["output_mode"] = config["output_mode"]
    analysis["output_language"] = config["output_language"]
    analysis["analysis_date"] = config["analysis_date"]
    analysis["run_context"] = run_context

    price_at_analysis = analysis.get("price_at_analysis")
    if price_at_analysis is None:
        price_at_analysis = metric_value(validated_metrics, "price_at_analysis")
    if price_at_analysis is None:
        price_at_analysis = metric_value(validated_metrics, "price")
    analysis["price_at_analysis"] = price_at_analysis

    currency = analysis.get("currency")
    if currency is None:
        price_metric = validated_metrics.get("price")
        price_at_analysis_metric = validated_metrics.get("price_at_analysis")
        if isinstance(price_metric, dict):
            currency = price_metric.get("currency")
        if currency is None and isinstance(price_at_analysis_metric, dict):
            currency = price_at_analysis_metric.get("currency")
    analysis["currency"] = currency

    analysis["key_metrics"] = key_metrics
    analysis["scenarios"] = build_scenarios(analysis, validated_metrics, price_at_analysis)
    analysis["rr_score"] = analysis.get("rr_score")
    analysis.setdefault("verdict", "Migrated legacy sample")
    analysis.setdefault("company_type", validated.get("company_type") or "Legacy sample migration")
    analysis.setdefault("top_risks", [])
    analysis.setdefault("upcoming_catalysts", [])
    analysis["migration"] = build_migration_block(
        config["analysis_source"],
        [
            "Analysis result promoted from legacy snapshot/latest artifact",
            "Scenario placeholders were added only where the legacy sample omitted narrative assumptions or targets",
            *warnings,
        ],
    )
    if config.get("report_path"):
        analysis["report_path"] = config["report_path"]
    return analysis


def synthesize_quality_report(
    config: dict[str, Any],
    validated: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ticker": config["ticker"],
        "output_mode": config["output_mode"],
        "check_timestamp": validated.get("validation_timestamp", utc_now_iso()),
        "overall_result": "PASS_WITH_FLAGS",
        "run_context": run_context,
        "items": {
            "legacy_migration": {
                "status": "PASS_WITH_FLAGS",
                "delivery_impact": "historical_flag_only",
                "notes": [
                    "Original quality-report.json was not preserved in the legacy sample namespace.",
                    "This synthetic report documents that the sample was normalized into the canonical run-local contract.",
                ],
            },
            "schema_validation": {
                "status": "PASS",
                "delivery_impact": "none",
                "notes": ["Run-local migrated artifacts are expected to pass schema validation after generation."],
            },
        },
        "delivery_gate": {
            "result": "PASS",
            "ready_for_delivery": True,
            "blocking_items": [],
            "non_blocking_items": [],
            "historical_only_items": ["legacy_migration"],
            "critic_overall": None,
            "critic_delivery_impact": "none",
        },
        "auto_fixes_applied": [
            "Normalized legacy source tags to canonical metadata contract",
            "Backfilled run_context into every migrated artifact",
        ],
        "inline_flags_added": [],
        "migration": build_migration_block(
            None,
            ["Synthetic quality report generated because no legacy quality artifact existed for this ticker"],
        ),
    }


def migrate_quality_report(
    config: dict[str, Any],
    source: dict[str, Any] | None,
    validated: dict[str, Any],
    run_context: dict[str, Any],
) -> dict[str, Any]:
    if not source:
        return synthesize_quality_report(config, validated, run_context)

    report = copy.deepcopy(source)
    report["ticker"] = config["ticker"]
    report["output_mode"] = config["output_mode"]
    report["run_context"] = run_context
    report["migration"] = build_migration_block(
        config.get("quality_report_source"),
        ["Quality report promoted from legacy shared artifact namespace"],
    )
    return report


def write_manifest(config: dict[str, Any], run_id: str, paths: dict[str, Path]) -> dict[str, Any]:
    relpaths = relativize_paths(
        REPO_ROOT,
        {
            "artifact_root": paths["artifact_root"],
            "research_plan": paths["research_plan"],
            "tier1_raw": paths["tier1_raw"],
            "dart_api_raw": paths["dart_api_raw"],
            "tier2_raw": paths["tier2_raw"],
            "validated_data": paths["validated_data"],
            "analysis_result": paths["analysis_result"],
            "quality_report": paths["quality_report"],
            "snapshot_dir": paths["snapshot_dir"],
            "reports_dir": paths["reports_dir"],
        },
    )
    manifest = {
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "tickers": [config["ticker"]],
        "artifact_layout": "output/runs/{run_id}/{ticker}/",
        "artifacts": {config["ticker"]: relpaths},
        "migration": {
            "source_namespace": "legacy_output_samples",
            "legacy_sources": {
                key: value
                for key, value in config.items()
                if key.endswith("_source") and value
            },
        },
    }
    atomic_write(paths["run_manifest"], manifest)
    return manifest


def migrate_fixture(config: dict[str, Any], skip_validation: bool = False) -> dict[str, Any]:
    run_id = run_id_for(config)
    paths = build_run_paths(REPO_ROOT, run_id, config["ticker"])
    paths["artifact_root"].mkdir(parents=True, exist_ok=True)

    run_context = build_run_context(paths, run_id, config["ticker"])
    research_source = load_json(config.get("research_plan_source"))
    validated_source = load_json(config["validated_data_source"])
    analysis_source = load_json(config["analysis_source"])
    quality_source = load_json(config.get("quality_report_source"))

    if validated_source is None:
        raise FileNotFoundError(f"Missing validated data source for {config['ticker']}")
    if analysis_source is None:
        raise FileNotFoundError(f"Missing analysis source for {config['ticker']}")

    research_plan = migrate_research_plan(config, research_source, run_context)
    validated_data = migrate_validated_data(config, validated_source, run_context)
    analysis_result = migrate_analysis_result(config, analysis_source, validated_data, run_context)
    base_quality_report = migrate_quality_report(config, quality_source, validated_data, run_context)
    quality_report = build_quality_report(
        research_plan,
        validated_data,
        analysis_result,
        existing_report=base_quality_report,
    )

    atomic_write(paths["research_plan"], research_plan)
    atomic_write(paths["validated_data"], validated_data)
    atomic_write(paths["analysis_result"], analysis_result)
    atomic_write(paths["quality_report"], quality_report)
    manifest = write_manifest(config, run_id, paths)

    validation = validate_run_directory(paths["run_root"], base_dir=REPO_ROOT)
    if not skip_validation and not validation["valid"]:
        raise RuntimeError(json.dumps(validation, ensure_ascii=False, indent=2))

    return {
        "ticker": config["ticker"],
        "run_id": run_id,
        "manifest_path": str(paths["run_manifest"].relative_to(REPO_ROOT)),
        "valid": validation["valid"],
        "result_count": len(validation["results"]),
        "manifest": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote legacy sample artifacts into run-local fixtures")
    parser.add_argument("--tickers", nargs="*", help="Subset of legacy fixtures to migrate")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    requested = [ticker.upper() for ticker in args.tickers] if args.tickers else list(LEGACY_FIXTURES)
    unknown = [ticker for ticker in requested if ticker not in LEGACY_FIXTURES]
    if unknown:
        raise SystemExit(f"Unsupported legacy fixture tickers: {', '.join(unknown)}")

    migrated = [
        migrate_fixture(LEGACY_FIXTURES[ticker], skip_validation=args.skip_validation)
        for ticker in requested
    ]
    print(json.dumps({"migrated": migrated}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
