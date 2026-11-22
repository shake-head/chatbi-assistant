"""OpenAI-compatible hosted model adapter."""

from __future__ import annotations

from decimal import Decimal

import httpx

from app.services.ai.base import AIProviderError, ProviderResult

JSON_MODE_INSTRUCTION = "Return one valid JSON object only. Do not wrap it in Markdown."


class OpenAICompatibleProvider:
    """Call any hosted provider that implements the chat completions contract."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> ProviderResult:
        """Call the remote chat completions endpoint once."""

        request_messages = list(messages)
        if json_mode:
            request_messages = [
                {"role": "system", "content": JSON_MODE_INSTRUCTION},
                *request_messages,
            ]

        body: dict[str, object] = {
            "model": self.model,
            "messages": request_messages,
            "temperature": 0,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_TIMEOUT", retriable=True) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("AI_TRANSPORT_ERROR", retriable=True) from exc

        if response.status_code >= 400:
            retriable = response.status_code == 429 or response.status_code >= 500
            raise AIProviderError(f"AI_HTTP_{response.status_code}", retriable=retriable)

        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            usage = payload.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI_INVALID_RESPONSE", retriable=False) from exc

        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI_EMPTY_RESPONSE", retriable=True)

        if prompt_tokens <= 0:
            prompt_tokens = _estimate_tokens("\n".join(message["content"] for message in messages))
        if completion_tokens <= 0:
            completion_tokens = _estimate_tokens(content)

        return ProviderResult(
            content=content,
            provider=self.name,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=Decimal("0"),
        )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
