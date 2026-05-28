from __future__ import annotations

from .anthropic_api import AnthropicBackend
from .base import AnalystBackend, BackendResult
from .codex_cli import CodexCliBackend
from .openai_api import OpenAIBackend
from .registry import load_model_config


def get_backend(
    name: str | None = None,
    *,
    logical_tier: str = "analyst_main",
) -> AnalystBackend:
    backend_name = (name or "").strip()
    if backend_name == "anthropic_api" and logical_tier == "analyst_main":
        logical_tier = "analyst_fallback"
    config = load_model_config(logical_tier=logical_tier)
    if not backend_name:
        provider = config["provider"].lower()
        backend_name = f"{provider}_api"

    if backend_name == "openai_api":
        return OpenAIBackend(config["model"])
    if backend_name == "anthropic_api":
        return AnthropicBackend(config["model"])
    if backend_name == "codex_cli":
        return CodexCliBackend(config["model"])
    raise ValueError(f"Unknown analyst backend: {backend_name}")


__all__ = ["AnalystBackend", "BackendResult", "get_backend"]
