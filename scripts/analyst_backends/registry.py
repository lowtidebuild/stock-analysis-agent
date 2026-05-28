from __future__ import annotations

import os
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "model_registry.yaml"


class ModelRegistryError(RuntimeError):
    pass


def load_model_config(
    *,
    logical_tier: str,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, str]:
    registry = parse_registry(registry_path)
    tiers = registry.get("logical_tiers")
    if not isinstance(tiers, dict):
        raise ModelRegistryError("model_registry.yaml missing logical_tiers")

    config = tiers.get(logical_tier)
    if not isinstance(config, dict):
        raise ModelRegistryError(f"Unknown logical tier: {logical_tier}")

    provider = str(config.get("provider") or "").strip()
    model = str(config.get("model") or "").strip()
    model_env = str(config.get("model_env") or "").strip()
    if model_env:
        model = os.environ.get(model_env, "").strip()

    if not provider:
        raise ModelRegistryError(f"{logical_tier} missing provider")
    if not model:
        raise ModelRegistryError(
            f"{logical_tier} missing model. Set {model_env or 'model'}."
        )

    return {"provider": provider, "model": model}


def parse_registry(path: Path) -> dict[str, Any]:
    """Parse the small YAML subset used by config/model_registry.yaml.

    The repo intentionally avoids adding PyYAML just for this bootstrap file.
    Supported shape is nested mappings with two-space indentation.
    """
    if not path.exists():
        raise ModelRegistryError(f"Missing model registry: {path}")

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if ":" not in raw_line:
            raise ModelRegistryError(f"Invalid registry line: {raw_line}")
        key, value = raw_line.strip().split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if value:
            current[key] = value
        else:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
    return root
