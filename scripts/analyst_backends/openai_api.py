from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import BackendResult


class OpenAIBackend:
    provider = "openai"

    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for openai_api backend.")

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
            "messages": [{"role": "system", "content": system}, *messages],
        }
        token_budget_key = (
            "max_completion_tokens"
            if self.model.startswith(("gpt-5", "o1", "o3", "o4"))
            else "max_tokens"
        )
        payload[token_budget_key] = max_tokens
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "analysis_result",
                    "schema": json_schema,
                    "strict": False,
                },
            }

        body = self._post("https://api.openai.com/v1/chat/completions", payload)
        message = body["choices"][0]["message"]
        content = message.get("content") or ""
        if json_schema is not None:
            parsed_json = self._parse_json_content(content, payload)
            if parsed_json is None:
                retry_payload = dict(payload)
                retry_payload[token_budget_key] = max(max_tokens * 2, max_tokens + 2000)
                body = self._post("https://api.openai.com/v1/chat/completions", retry_payload)
                message = body["choices"][0]["message"]
                content = message.get("content") or ""
                parsed_json = self._parse_json_content(content, retry_payload, raise_on_error=True)
        else:
            parsed_json = None
        usage = body.get("usage") or {}
        return BackendResult(
            json=parsed_json,
            model=body.get("model") or self.model,
            provider=self.provider,
            text=content,
            usage={
                "prompt": usage.get("prompt_tokens"),
                "completion": usage.get("completion_tokens"),
                "total": usage.get("total_tokens"),
            },
        )

    def _parse_json_content(
        self,
        content: str,
        payload: dict[str, Any],
        *,
        raise_on_error: bool = False,
    ) -> dict[str, Any] | None:
        text = content.strip()
        if not text:
            if raise_on_error:
                raise RuntimeError(
                    f"OpenAI structured output was empty after retry; token_budget={payload.get('max_completion_tokens') or payload.get('max_tokens')}"
                )
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            if raise_on_error:
                preview = text[:240].replace("\n", " ")
                raise RuntimeError(f"OpenAI structured output was not valid JSON after retry: {preview}") from exc
            return None
        if not isinstance(parsed, dict):
            if raise_on_error:
                raise RuntimeError("OpenAI structured output JSON must be an object.")
            return None
        return parsed

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {detail[:800]}") from exc
