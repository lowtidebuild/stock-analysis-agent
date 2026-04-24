from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.analysis_contract import normalize_metric_entry
from tools.paths import runtime_path

RAW_ARTIFACT_FILENAMES = (
    "tier1-raw.json",
    "tier2-raw.json",
    "dart-api-raw.json",
    "yfinance-raw.json",
    "fred-snapshot.json",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _date_part(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _compact_exclusion(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        metric = item.get("metric") or item.get("name")
        reason = item.get("reason") or item.get("exclusion_reason")
        display = item.get("display", "—")
        return {
            "metric": str(metric) if metric else None,
            "reason": str(reason) if reason else None,
            "display": display,
        }
    return {"metric": str(item), "reason": None, "display": "—"}


def _compact_conflict(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"summary": str(item)}

    candidates = item.get("candidates")
    compact = {
        "metric": item.get("metric"),
        "summary": item.get("summary") or item.get("selection_reason") or item.get("reason"),
        "candidate_count": len(candidates) if isinstance(candidates, list) else None,
        "selected_candidate_id": item.get("selected_candidate_id"),
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [])}


def _metric_claim(metric_name: str, value: Any, unit: Any = None, currency: Any = None) -> str:
    suffix_parts = [str(part) for part in (unit, currency) if part not in (None, "")]
    suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ""
    return f"{metric_name} is {value}{suffix}"


def _fact_from_metric(
    metric_name: str,
    metric_entry: Any,
    *,
    market: str | None,
    fact_index: int,
) -> dict[str, Any] | None:
    if not isinstance(metric_entry, dict):
        metric_entry = {"value": metric_entry}

    normalized, _warnings = normalize_metric_entry(metric_name, metric_entry, market=market)
    grade = normalized.get("grade")
    value = normalized.get("value")
    if grade not in {"A", "B", "C"} or value is None:
        return None

    unit = normalized.get("unit")
    currency = normalized.get("currency")
    fact = {
        "id": f"fact_{fact_index:03d}",
        "metric": metric_name,
        "claim": _metric_claim(metric_name, value, unit=unit, currency=currency),
        "value": value,
        "unit": unit,
        "currency": currency,
        "grade": grade,
        "display_tag": normalized.get("display_tag"),
        "source_type": normalized.get("source_type"),
        "source_authority": normalized.get("source_authority"),
        "sources": [str(source) for source in _as_list(normalized.get("sources")) if str(source).strip()],
        "as_of_date": normalized.get("as_of_date"),
        "period_end": normalized.get("period_end"),
        "notes": normalized.get("notes"),
    }
    candidate_trace = normalized.get("candidate_trace")
    if isinstance(candidate_trace, dict):
        fact["candidate_trace"] = {
            key: candidate_trace.get(key)
            for key in ("selected_candidate_id", "source_query_ids", "selection_reason")
            if candidate_trace.get(key) not in (None, "", [])
        }
    return {key: value for key, value in fact.items() if value not in (None, "", [])}


def infer_raw_artifact_refs(validated_data_path: str | Path) -> list[str]:
    path = runtime_path(validated_data_path)
    ticker_dir = path.parent
    refs = []
    for filename in RAW_ARTIFACT_FILENAMES:
        candidate = ticker_dir / filename
        if candidate.exists():
            refs.append(str(candidate))
    return refs


def build_evidence_pack(
    validated_data: dict[str, Any],
    *,
    raw_artifact_refs: Iterable[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    market = validated_data.get("market")
    facts: list[dict[str, Any]] = []
    for metric_name, metric_entry in (validated_data.get("validated_metrics") or {}).items():
        fact = _fact_from_metric(metric_name, metric_entry, market=market, fact_index=len(facts) + 1)
        if fact is not None:
            facts.append(fact)

    exclusions = [_compact_exclusion(item) for item in _as_list(validated_data.get("exclusions"))]
    excluded_metrics = {item.get("metric") for item in exclusions if isinstance(item, dict)}
    for metric_name, metric_entry in (validated_data.get("validated_metrics") or {}).items():
        if metric_name in excluded_metrics or not isinstance(metric_entry, dict):
            continue
        if metric_entry.get("grade") == "D":
            exclusions.append(
                {
                    "metric": metric_name,
                    "reason": metric_entry.get("exclusion_reason"),
                    "display": "—",
                }
            )

    refs = []
    seen_refs = set()
    for ref in raw_artifact_refs or []:
        ref_text = str(ref)
        if ref_text and ref_text not in seen_refs:
            refs.append(ref_text)
            seen_refs.add(ref_text)

    generated = generated_at or utc_now_iso()
    pack: dict[str, Any] = {
        "ticker": validated_data.get("ticker"),
        "market": market,
        "as_of": _date_part(validated_data.get("validation_timestamp")) or _date_part(generated),
        "generated_at": generated,
        "run_context": validated_data.get("run_context"),
        "facts": facts,
        "exclusions": [item for item in exclusions if item.get("metric")],
        "conflicts": [_compact_conflict(item) for item in _as_list(validated_data.get("metric_conflicts"))],
        "raw_artifact_refs": refs,
        "raw_access_policy": {
            "default_load": "deny",
            "raw_access_log_required": True,
            "allowed_reasons": [
                "validator_conflict_review",
                "grade_c_or_d_metric_recheck",
                "critic_source_mismatch",
            ],
        },
    }
    for key in ("data_mode", "requested_mode", "effective_mode", "source_profile", "source_tier", "confidence_cap"):
        value = validated_data.get(key)
        if value is not None:
            pack[key] = value
    if validated_data.get("macro_context") is not None:
        pack["macro_context"] = validated_data.get("macro_context")
    return pack


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = runtime_path(path)
    with open(resolved, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {resolved}")
    return data


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    resolved = runtime_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_suffix(f"{resolved.suffix}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(resolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a compact evidence-pack.json from validated-data.json")
    parser.add_argument("--validated-data", required=True, help="Path to run-local validated-data.json")
    parser.add_argument("--output", required=True, help="Path to write evidence-pack.json")
    parser.add_argument(
        "--raw-artifact-ref",
        action="append",
        default=None,
        help="Raw artifact reference to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--no-infer-raw-refs",
        action="store_true",
        help="Do not infer sibling raw artifact refs from the validated-data directory.",
    )
    args = parser.parse_args(argv)

    validated = load_json(args.validated_data)
    raw_refs = list(args.raw_artifact_ref or [])
    if not args.no_infer_raw_refs:
        raw_refs.extend(infer_raw_artifact_refs(args.validated_data))
    pack = build_evidence_pack(validated, raw_artifact_refs=raw_refs)
    write_json(args.output, pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
