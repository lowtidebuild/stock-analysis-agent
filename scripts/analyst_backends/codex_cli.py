from __future__ import annotations


class CodexCliBackend:
    def __init__(self, model: str) -> None:
        self.model = model

    def complete(self, **_: object) -> object:
        # TODO: Add OAuth-backed Codex CLI backend after API backends are stable.
        raise NotImplementedError("codex_cli backend is intentionally out of scope.")
