from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools.paths import runtime_path

POINTER_KIND = "stock-analysis.latest-snapshot-pointer"
POINTER_SCHEMA_VERSION = "1.0"
DEFAULT_FRESHNESS_TTL_HOURS = 24

PROMOTED_ARTIFACTS = (
    ("analysis_result", "analysis-result.json"),
    ("validated_data", "validated-data.json"),
    ("quality_report", "quality-report.json"),
    ("evidence_pack", "evidence-pack.json"),
    ("tier1_raw", "tier1-raw.json"),
    ("dart_api_raw", "dart-api-raw.json"),
    ("tier2_raw", "tier2-raw.json"),
)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def display_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_stored_path(value: str | Path, base_dir: Path, pointer_path: Path | None = None) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    if candidate.parts and candidate.parts[0] == "output":
        runtime_candidate = runtime_path(candidate).resolve()
        if runtime_candidate.exists() or pointer_path is None:
            return runtime_candidate

    base_candidate = (base_dir / candidate).resolve()
    if base_candidate.exists() or pointer_path is None:
        return base_candidate

    runtime_candidate = runtime_path(candidate).resolve()
    if runtime_candidate.exists():
        return runtime_candidate

    return (pointer_path.parent / candidate).resolve()


def _safe_snapshot_part(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-")
    return cleaned[:96] or "snapshot"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_snapshot_metadata(snapshot: dict[str, Any], ticker: str) -> dict[str, Any]:
    data = dict(snapshot)
    data.setdefault("ticker", ticker.upper())
    data.setdefault("analysis_date", datetime.now(timezone.utc).date().isoformat())
    data.setdefault("snapshot_saved_at", utc_now_iso())
    return data


def build_snapshot_id(snapshot: dict[str, Any]) -> str:
    analysis_date = _safe_snapshot_part(snapshot.get("analysis_date") or datetime.now(timezone.utc).date().isoformat())
    run_context = snapshot.get("run_context") if isinstance(snapshot.get("run_context"), dict) else {}
    run_id = run_context.get("run_id")
    if run_id:
        return f"{analysis_date}_run_{_safe_snapshot_part(run_id)}"

    saved_at = _parse_datetime(snapshot.get("snapshot_saved_at")) or datetime.now(timezone.utc)
    stamp = saved_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{analysis_date}_saved_{stamp}"


def freshness_expiry(snapshot: dict[str, Any], ttl_hours: int = DEFAULT_FRESHNESS_TTL_HOURS) -> str:
    saved_at = _parse_datetime(snapshot.get("snapshot_saved_at")) or datetime.now(timezone.utc)
    return (saved_at + timedelta(hours=ttl_hours)).isoformat(timespec="seconds").replace("+00:00", "Z")


def promote_snapshot_artifacts(
    *,
    source_analysis_path: Path,
    snapshot_root: Path,
    snapshot: dict[str, Any],
    base_dir: Path,
) -> dict[str, str]:
    snapshot_root.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}
    source_dir = source_analysis_path.parent.resolve()

    for ref_key, filename in PROMOTED_ARTIFACTS:
        destination = snapshot_root / filename
        if ref_key == "analysis_result":
            atomic_write_json(destination, snapshot)
            refs[ref_key] = display_path(destination, base_dir)
            continue

        source = source_dir / filename
        if source.exists() and source.is_file():
            shutil.copy2(source, destination)
            refs[ref_key] = display_path(destination, base_dir)

    return refs


def build_latest_pointer(
    *,
    ticker: str,
    snapshot: dict[str, Any],
    snapshot_id: str,
    refs: dict[str, str],
) -> dict[str, Any]:
    pointer: dict[str, Any] = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "kind": POINTER_KIND,
        "ticker": ticker.upper(),
        "latest_snapshot_id": snapshot_id,
        "analysis_date": snapshot.get("analysis_date"),
        "snapshot_saved_at": snapshot.get("snapshot_saved_at"),
        "expires_at": freshness_expiry(snapshot),
        "freshness_ttl_hours": DEFAULT_FRESHNESS_TTL_HOURS,
        "data_mode": snapshot.get("data_mode"),
        "output_mode": snapshot.get("output_mode"),
        "rr_score": snapshot.get("rr_score"),
        "verdict": snapshot.get("verdict"),
        "price_at_analysis": snapshot.get("price_at_analysis"),
        "refs": refs,
    }

    for optional_key in ("market", "company_name", "currency"):
        if optional_key in snapshot:
            pointer[optional_key] = snapshot.get(optional_key)

    return pointer


def is_latest_pointer(data: dict[str, Any]) -> bool:
    return data.get("kind") == POINTER_KIND or (
        "latest_snapshot_id" in data and isinstance(data.get("refs"), dict)
    )


def resolve_pointer_snapshot_path(pointer: dict[str, Any], pointer_path: Path, base_dir: Path) -> Path:
    refs = pointer.get("refs") if isinstance(pointer.get("refs"), dict) else {}
    ref = refs.get("analysis_result") or refs.get("snapshot")
    if ref:
        return resolve_stored_path(str(ref), base_dir, pointer_path=pointer_path)

    snapshot_id = pointer.get("latest_snapshot_id")
    if not snapshot_id:
        raise ValueError(f"Latest pointer has no analysis_result ref or latest_snapshot_id: {pointer_path}")
    return (pointer_path.parent / "snapshots" / str(snapshot_id) / "analysis-result.json").resolve()


def load_snapshot_document(path: Path, base_dir: Path) -> dict[str, Any]:
    data = read_json(path)
    if not is_latest_pointer(data):
        return data

    snapshot_path = resolve_pointer_snapshot_path(data, path, base_dir)
    return read_json(snapshot_path)


def iter_snapshot_entries(ticker_dir: Path, ticker: str, base_dir: Path) -> list[dict[str, Any]]:
    ticker_upper = ticker.upper()
    entries: list[dict[str, Any]] = []

    for path in sorted((ticker_dir / "snapshots").glob("*/analysis-result.json"), reverse=True):
        try:
            data = read_json(path)
            entries.append({
                "snapshot_id": path.parent.name,
                "analysis_date": data.get("analysis_date", "unknown"),
                "path": path,
                "path_display": display_path(path, base_dir),
                "data": data,
                "storage": "snapshot_dir",
            })
        except Exception as exc:
            entries.append({
                "snapshot_id": path.parent.name,
                "analysis_date": "unknown",
                "path": path,
                "path_display": display_path(path, base_dir),
                "error": str(exc),
                "storage": "snapshot_dir",
            })

    legacy_pattern = f"{ticker_upper}_*_snapshot.json"
    for path in sorted(ticker_dir.glob(legacy_pattern), reverse=True):
        try:
            data = read_json(path)
            entries.append({
                "snapshot_id": path.stem,
                "analysis_date": data.get("analysis_date", "unknown"),
                "path": path,
                "path_display": display_path(path, base_dir),
                "data": data,
                "storage": "legacy_flat_file",
            })
        except Exception as exc:
            entries.append({
                "snapshot_id": path.stem,
                "analysis_date": "unknown",
                "path": path,
                "path_display": display_path(path, base_dir),
                "error": str(exc),
                "storage": "legacy_flat_file",
            })

    entries.sort(key=lambda entry: (str(entry.get("analysis_date", "")), str(entry.get("snapshot_id", ""))), reverse=True)
    return entries
