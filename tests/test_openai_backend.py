from __future__ import annotations

import json

from scripts.analyst_backends.openai_api import OpenAIBackend


def test_openai_backend_retries_empty_structured_content(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    backend = OpenAIBackend("gpt-5.5")
    calls: list[dict[str, object]] = []

    def fake_post(_url: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        content = "" if len(calls) == 1 else json.dumps({"ticker": "AAPL"})
        return {
            "choices": [{"message": {"content": content}}],
            "model": "gpt-5.5-test",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(backend, "_post", fake_post)

    result = backend.complete(
        system="Return JSON.",
        messages=[{"role": "user", "content": "{}"}],
        json_schema={"type": "object"},
        max_tokens=100,
    )

    assert result.json == {"ticker": "AAPL"}
    assert len(calls) == 2
    assert calls[1]["max_completion_tokens"] == 2100
