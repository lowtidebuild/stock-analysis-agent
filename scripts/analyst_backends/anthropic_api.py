from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import BackendResult


class AnthropicBackend:
    provider = "anthropic"

    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required for anthropic_api backend."
            )

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        max_tokens: int,
    ) -> BackendResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if json_schema is not None:
            payload["tools"] = [
                {
                    "name": "emit_analysis_result",
                    "description": "Emit the final analysis-result JSON.",
                    "input_schema": json_schema,
                }
            ]
            payload["tool_choice"] = {
                "type": "tool",
                "name": "emit_analysis_result",
            }

        body = self._post("https://api.anthropic.com/v1/messages", payload)
        parsed_json: dict[str, Any] | None = None
        text_parts: list[str] = []
        for part in body.get("content", []):
            if part.get("type") == "tool_use" and part.get("name") == "emit_analysis_result":
                parsed_json = part.get("input")
            if part.get("type") == "text":
                text_parts.append(part.get("text") or "")

        usage = body.get("usage") or {}
        return BackendResult(
            json=parsed_json,
            model=body.get("model") or self.model,
            provider=self.provider,
            text="\n".join(text_parts) or None,
            usage={
                "prompt": usage.get("input_tokens"),
                "completion": usage.get("output_tokens"),
                "total": (usage.get("input_tokens") or 0)
                + (usage.get("output_tokens") or 0),
            },
        )

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API error {exc.code}: {detail[:800]}") from exc
