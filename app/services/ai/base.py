"""AI provider contracts shared by the gateway and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    """Normalized result returned by any model provider."""

    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal = Decimal("0")


class AIProviderError(Exception):
    """A provider failure with a stable internal code and retry hint."""

    def __init__(self, code: str, *, retriable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retriable = retriable


class AIProvider(Protocol):
    """Minimal provider interface implemented behind the AI gateway."""

    name: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> ProviderResult:
        """Return one normalized completion."""
        ...
