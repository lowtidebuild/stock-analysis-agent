from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendResult:
    json: dict[str, Any] | None
    model: str
    provider: str
    text: str | None
    usage: dict[str, int | None]


class AnalystBackend(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        max_tokens: int,
    ) -> BackendResult:
        """Return structured analyst output plus model metadata."""
