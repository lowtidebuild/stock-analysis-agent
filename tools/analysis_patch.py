from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from tools.analysis_contract import utc_now_iso


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_json_path(path: str) -> list[str | int]:
    normalized = path.strip()
    if normalized in {"", "$"}:
        return []
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:]

    tokens: list[str | int] = []
    buffer = ""
    index = 0
    while index < len(normalized):
        char = normalized[index]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            index += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            closing = normalized.find("]", index)
            if closing == -1:
                raise ValueError(f"Unclosed index in path: {path}")
            raw_index = normalized[index + 1:closing]
            if not raw_index.isdigit():
                raise ValueError(f"Non-numeric index {raw_index!r} in path: {path}")
            tokens.append(int(raw_index))
            index = closing + 1
            continue
        buffer += char
        index += 1
    if buffer:
        tokens.append(buffer)
    return tokens


def normalize_json_path(path: str) -> str:
    normalized = path.strip()
    if normalized == "$":
        return "$"
    if normalized.startswith("$."):
        return normalized
    if normalized.startswith("$"):
        return f"$.{normalized[1:].lstrip('.')}"
    return f"$.{normalized.lstrip('.')}"


def task_target_to_json_path(target: str) -> str:
    return normalize_json_path(target)


def path_is_allowed(path: str, allowed_targets: list[str]) -> bool:
    path_tokens = parse_json_path(normalize_json_path(path))
    for target in allowed_targets:
        target_tokens = parse_json_path(task_target_to_json_path(target))
        if path_tokens[: len(target_tokens)] == target_tokens:
            return True
    return False


def build_task_map(patch_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    task_map: dict[str, dict[str, Any]] = {}
    for task in patch_plan.get("tasks", []):
        if isinstance(task, dict) and isinstance(task.get("task_id"), str):
            task_map[task["task_id"]] = task
    return task_map


def required_analysis_task_ids(patch_plan: dict[str, Any]) -> list[str]:
    task_ids: list[str] = []
    for task in patch_plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id")
        edit_scope = task.get("edit_scope")
        analysis_targets = task.get("analysis_targets")
        if (
            isinstance(task_id, str)
            and edit_scope == "analysis_json_and_render"
            and isinstance(analysis_targets, list)
            and analysis_targets
        ):
            task_ids.append(task_id)
    return task_ids


def unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def normalize_analysis_patch(
    raw_patch: dict[str, Any],
    patch_plan: dict[str, Any],
    patch_plan_path: str,
    source_analysis_result_path: str,
    target_analysis_result_path: str,
) -> dict[str, Any]:
    raw_updates = raw_patch.get("updates")
    normalized_updates: list[dict[str, Any]] = []
    if isinstance(raw_updates, list):
        for update in raw_updates:
            if not isinstance(update, dict):
                continue
            task_id = update.get("task_id")
            path = update.get("path")
            if not isinstance(task_id, str) or not isinstance(path, str):
                continue
            normalized_updates.append(
                {
                    "task_id": task_id,
                    "path": normalize_json_path(path),
                    "value": update.get("value"),
                    "rationale": update.get("rationale"),
                }
            )

    task_ids = raw_patch.get("task_ids") if isinstance(raw_patch.get("task_ids"), list) else None
    if task_ids is None:
        task_ids = [update["task_id"] for update in normalized_updates]
    normalized_task_ids = unique_preserving_order([task_id for task_id in task_ids if isinstance(task_id, str)])
    updated_paths = [update["path"] for update in normalized_updates]
    task_map = build_task_map(patch_plan)
    render_required = any(
        bool(task_map.get(task_id, {}).get("render_step_required"))
        for task_id in normalized_task_ids
    )

    normalized = {
        "ticker": patch_plan.get("ticker"),
        "output_mode": patch_plan.get("output_mode"),
        "run_context": patch_plan.get("run_context") or {},
        "patch_plan_path": patch_plan_path,
        "source_analysis_result_path": source_analysis_result_path,
        "target_analysis_result_path": target_analysis_result_path,
        "task_ids": normalized_task_ids,
        "updated_paths": updated_paths,
        "render_required": render_required,
        "preserve_untouched_sections": True,
        "updates": normalized_updates,
        "applied_by": raw_patch.get("applied_by") or "analyst-patch-executor",
        "applied_at": raw_patch.get("applied_at") or utc_now_iso(),
    }
    if isinstance(raw_patch.get("notes"), list):
        normalized["notes"] = raw_patch.get("notes")
    return normalized


def validate_against_patch_plan(
    analysis_patch: dict[str, Any],
    patch_plan: dict[str, Any],
    path: str = "$",
) -> list[str]:
    errors: list[str] = []
    task_map = build_task_map(patch_plan)
    required_task_ids = required_analysis_task_ids(patch_plan)
    patch_task_ids = analysis_patch.get("task_ids")
    updates = analysis_patch.get("updates")
    updated_paths = analysis_patch.get("updated_paths")

    if analysis_patch.get("ticker") != patch_plan.get("ticker"):
        errors.append(f"{path}.ticker: expected {patch_plan.get('ticker')!r} from patch-plan")
    if analysis_patch.get("output_mode") != patch_plan.get("output_mode"):
        errors.append(f"{path}.output_mode: expected {patch_plan.get('output_mode')!r} from patch-plan")

    patch_context = analysis_patch.get("run_context") if isinstance(analysis_patch.get("run_context"), dict) else {}
    plan_context = patch_plan.get("run_context") if isinstance(patch_plan.get("run_context"), dict) else {}
    for key in ("run_id", "artifact_root", "ticker"):
        if patch_context.get(key) != plan_context.get(key):
            errors.append(f"{path}.run_context.{key}: expected {plan_context.get(key)!r} from patch-plan")

    if not isinstance(patch_task_ids, list):
        errors.append(f"{path}.task_ids: expected array")
        patch_task_ids = []
    if not isinstance(updates, list):
        errors.append(f"{path}.updates: expected array")
        updates = []
    if not isinstance(updated_paths, list):
        errors.append(f"{path}.updated_paths: expected array")
        updated_paths = []

    expected_task_ids = unique_preserving_order(required_task_ids)
    actual_task_ids = unique_preserving_order([task_id for task_id in patch_task_ids if isinstance(task_id, str)])
    if actual_task_ids != expected_task_ids:
        errors.append(f"{path}.task_ids: expected {expected_task_ids!r} from patch-plan actionable tasks, got {actual_task_ids!r}")

    if patch_plan.get("ready_for_redelivery") is True and updates:
        errors.append(f"{path}.updates: patch-plan is already ready_for_redelivery, so no analysis updates are allowed")

    update_task_ids: list[str] = []
    normalized_update_paths: list[str] = []
    for index, update in enumerate(updates):
        if not isinstance(update, dict):
            errors.append(f"{path}.updates[{index}]: expected object payload")
            continue
        task_id = update.get("task_id")
        update_path = update.get("path")
        rationale = update.get("rationale")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"{path}.updates[{index}].task_id: missing task id")
            continue
        if not isinstance(update_path, str) or not update_path:
            errors.append(f"{path}.updates[{index}].path: missing JSON path")
            continue
        normalized_path = normalize_json_path(update_path)
        normalized_update_paths.append(normalized_path)
        update_task_ids.append(task_id)

        task = task_map.get(task_id)
        if task is None:
            errors.append(f"{path}.updates[{index}].task_id: {task_id!r} is not present in patch-plan")
            continue
        allowed_targets = task.get("analysis_targets") if isinstance(task.get("analysis_targets"), list) else []
        if not allowed_targets:
            errors.append(f"{path}.updates[{index}].task_id: task {task_id!r} has no analysis targets in patch-plan")
            continue
        if not path_is_allowed(normalized_path, allowed_targets):
            errors.append(
                f"{path}.updates[{index}].path: {normalized_path!r} is outside allowed targets {allowed_targets!r} for task {task_id!r}"
            )
        if not isinstance(rationale, str) or not rationale:
            errors.append(f"{path}.updates[{index}].rationale: missing rationale")

    expected_updated_paths = [normalize_json_path(path_value) for path_value in updated_paths if isinstance(path_value, str)]
    if normalized_update_paths != expected_updated_paths:
        errors.append(
            f"{path}.updated_paths: expected {normalized_update_paths!r} to match updates order, got {expected_updated_paths!r}"
        )

    if unique_preserving_order(update_task_ids) != actual_task_ids:
        errors.append(
            f"{path}.task_ids: expected task_ids to match update coverage {unique_preserving_order(update_task_ids)!r}, got {actual_task_ids!r}"
        )

    task_ids_with_updates = set(update_task_ids)
    missing_updates = [task_id for task_id in expected_task_ids if task_id not in task_ids_with_updates]
    if missing_updates:
        errors.append(f"{path}.updates: missing update payloads for required patch tasks {missing_updates!r}")

    expected_render_required = any(
        bool(task_map.get(task_id, {}).get("render_step_required"))
        for task_id in expected_task_ids
    )
    if analysis_patch.get("render_required") != expected_render_required:
        errors.append(
            f"{path}.render_required: expected {expected_render_required!r} from patch-plan, got {analysis_patch.get('render_required')!r}"
        )
    if analysis_patch.get("preserve_untouched_sections") is not True:
        errors.append(f"{path}.preserve_untouched_sections: must be true")

    return errors


def set_json_path(payload: Any, path: str, value: Any) -> None:
    tokens = parse_json_path(normalize_json_path(path))
    if not tokens:
        raise ValueError("Refusing to replace the entire document root")

    current = payload
    for index, token in enumerate(tokens[:-1]):
        next_token = tokens[index + 1]
        if isinstance(token, int):
            if not isinstance(current, list):
                raise ValueError(f"{path}: expected list before index [{token}]")
            if token >= len(current):
                raise ValueError(f"{path}: list index [{token}] is out of bounds")
            current = current[token]
            continue

        if not isinstance(current, dict):
            raise ValueError(f"{path}: expected object before key {token!r}")
        if token not in current:
            current[token] = [] if isinstance(next_token, int) else {}
        current = current[token]

    final_token = tokens[-1]
    if isinstance(final_token, int):
        if not isinstance(current, list):
            raise ValueError(f"{path}: expected list before final index [{final_token}]")
        if final_token >= len(current):
            raise ValueError(f"{path}: list index [{final_token}] is out of bounds")
        current[final_token] = value
        return

    if not isinstance(current, dict):
        raise ValueError(f"{path}: expected object before final key {final_token!r}")
    current[final_token] = value


def apply_analysis_patch(
    analysis_result: dict[str, Any],
    analysis_patch: dict[str, Any],
    patch_plan: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_against_patch_plan(analysis_patch, patch_plan)
    if errors:
        raise ValueError("; ".join(errors))

    updated = copy.deepcopy(analysis_result)
    for update in analysis_patch.get("updates", []):
        set_json_path(updated, update["path"], update.get("value"))
    return updated
