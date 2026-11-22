"""The single AI gateway used by all business services."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppException
from app.core.metrics import AI_COST_USD_TOTAL, AI_REQUESTS_TOTAL
from app.models import AIUsage
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.local_provider import LocalRuleProvider
from app.services.ai.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AICompletion:
    """Successful gateway output plus metering details."""

    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int


class AIGateway:
    """Unified model invocation, retry, fallback, and cost accounting."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.providers = self._build_providers()

    def _build_providers(self) -> list[AIProvider]:
        if self.settings.ai_provider == "local":
            if self.settings.app_env == "production":
                raise AppException(
                    code="AI_NOT_CONFIGURED",
                    message="The local AI provider is disabled in production",
                    status_code=503,
                )
            return [LocalRuleProvider()]

        remote_configured = bool(
            self.settings.ai_api_base_url.strip() and self.settings.ai_model.strip()
        )
        if remote_configured:
            providers: list[AIProvider] = [
                OpenAICompatibleProvider(
                    base_url=self.settings.ai_api_base_url,
                    model=self.settings.ai_model,
                    api_key=(
                        self.settings.ai_api_key.get_secret_value()
                        if self.settings.ai_api_key
                        else None
                    ),
                    timeout_seconds=self.settings.ai_timeout_seconds,
                )
            ]
            if self.settings.app_env != "production":
                providers.append(LocalRuleProvider())
            return providers

        if self.settings.ai_provider == "openai_compatible":
            raise AppException(
                code="AI_NOT_CONFIGURED",
                message="AI_API_BASE_URL and AI_MODEL must be configured",
                status_code=503,
            )
        if self.settings.app_env == "production":
            raise AppException(
                code="AI_NOT_CONFIGURED",
                message="A hosted AI provider must be configured in production",
                status_code=503,
            )
        return [LocalRuleProvider()]

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        operation: str,
        user_id: int | None,
        conversation_id: int | None = None,
        json_mode: bool = False,
    ) -> AICompletion:
        """Call the provider chain and persist exactly one usage record."""

        self._enforce_monthly_budget(user_id)
        started_at = time.perf_counter()
        last_provider = self.providers[0]
        last_error: AIProviderError | None = None

        for provider in self.providers:
            last_provider = provider
            for attempt in range(self.settings.ai_max_retries + 1):
                attempt_started = time.perf_counter()
                try:
                    result = await provider.complete(messages, json_mode=json_mode)
                    latency_ms = int((time.perf_counter() - attempt_started) * 1000)
                    cost = self._calculate_cost(result.prompt_tokens, result.completion_tokens)
                    self._record_usage(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        operation=operation,
                        provider=result.provider,
                        model=result.model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                        success=True,
                    )
                    logger.info(
                        "ai_call operation=%s provider=%s model=%s tokens=%s cost_usd=%s "
                        "latency_ms=%s success=true",
                        operation,
                        result.provider,
                        result.model,
                        result.prompt_tokens + result.completion_tokens,
                        cost,
                        latency_ms,
                    )
                    AI_REQUESTS_TOTAL.labels(
                        operation=operation,
                        provider=result.provider,
                        status="success",
                    ).inc()
                    AI_COST_USD_TOTAL.labels(
                        operation=operation,
                        provider=result.provider,
                    ).inc(float(cost))
                    return AICompletion(
                        content=result.content,
                        provider=result.provider,
                        model=result.model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                    )
                except AIProviderError as exc:
                    last_error = exc
                    logger.warning(
                        "ai_attempt_failed operation=%s provider=%s attempt=%s error=%s",
                        operation,
                        provider.name,
                        attempt + 1,
                        exc.code,
                    )
                    if not exc.retriable:
                        break
                    if attempt < self.settings.ai_max_retries:
                        await asyncio.sleep(min(0.2 * (2**attempt), 1.0))
                except Exception:
                    last_error = AIProviderError("AI_UNEXPECTED_ERROR", retriable=False)
                    logger.exception(
                        "ai_attempt_unexpected operation=%s provider=%s",
                        operation,
                        provider.name,
                    )
                    break

        total_latency = int((time.perf_counter() - started_at) * 1000)
        self._record_usage(
            user_id=user_id,
            conversation_id=conversation_id,
            operation=operation,
            provider=last_provider.name,
            model=getattr(last_provider, "model", "unknown"),
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=total_latency,
            success=False,
            error_code=last_error.code if last_error else "AI_SERVICE_UNAVAILABLE",
        )
        AI_REQUESTS_TOTAL.labels(
            operation=operation,
            provider=last_provider.name,
            status="failure",
        ).inc()
        raise AppException(
            code="AI_SERVICE_UNAVAILABLE",
            message="The analysis service is temporarily unavailable",
            status_code=503,
        )

    def _enforce_monthly_budget(self, user_id: int | None) -> None:
        if user_id is None:
            return
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent = self.db.scalar(
            select(func.coalesce(func.sum(AIUsage.cost_usd), 0)).where(
                AIUsage.user_id == user_id,
                AIUsage.success.is_(True),
                AIUsage.created_at >= month_start,
            )
        )
        if Decimal(str(spent or 0)) >= Decimal(str(self.settings.ai_monthly_budget_usd)):
            raise AppException(
                code="AI_QUOTA_EXCEEDED",
                message="The monthly AI usage quota has been exceeded",
                status_code=429,
            )

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        input_cost = (
            Decimal(prompt_tokens)
            * Decimal(str(self.settings.ai_input_cost_per_million_usd))
            / Decimal(1_000_000)
        )
        output_cost = (
            Decimal(completion_tokens)
            * Decimal(str(self.settings.ai_output_cost_per_million_usd))
            / Decimal(1_000_000)
        )
        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    def _record_usage(self, **values: object) -> None:
        try:
            self.db.add(AIUsage(**values))
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("ai_usage_record_failed operation=%s", values.get("operation"))
