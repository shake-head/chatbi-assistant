"""AI gateway fallback, usage metering, and quota tests."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppException
from app.models import AIUsage, User
from app.services.ai.base import AIProviderError, ProviderResult
from app.services.ai.local_provider import LocalRuleProvider
from app.services.ai_gateway import AIGateway

INTENT_MESSAGES = [
    {"role": "system", "content": "Return JSON only."},
    {
        "role": "user",
        "content": json.dumps(
            {
                "task": "intent",
                "question": "各区域销售额合计",
                "schema": {
                    "columns": [
                        {"name": "region", "dtype": "string"},
                        {"name": "amount", "dtype": "number"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
    },
]


class FailingProvider:
    name = "failing"
    model = "failing-model"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> ProviderResult:
        raise AIProviderError("PROVIDER_DOWN", retriable=False)


def test_gateway_falls_back_and_records_success(
    db_session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(_env_file=None, app_env="test", ai_provider="local")
    with db_session_factory() as db:
        user = User(email="gateway@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        gateway = AIGateway(db, settings)
        gateway.providers = [FailingProvider(), LocalRuleProvider()]

        result = asyncio.run(
            gateway.complete(
                INTENT_MESSAGES,
                operation="intent",
                user_id=user.id,
                json_mode=True,
            )
        )

        assert result.provider == "local"
        assert '"metrics"' in result.content
        usage = db.scalar(select(AIUsage))
        assert usage is not None
        assert usage.success is True
        assert usage.provider == "local"


def test_usage_is_recorded_once_per_successful_gateway_call(
    db_session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(_env_file=None, app_env="test", ai_provider="local")
    with db_session_factory() as db:
        user = User(email="metered@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        gateway = AIGateway(db, settings)
        asyncio.run(
            gateway.complete(
                INTENT_MESSAGES,
                operation="intent",
                user_id=user.id,
                json_mode=True,
            )
        )
        asyncio.run(
            gateway.complete(
                INTENT_MESSAGES,
                operation="intent",
                user_id=user.id,
                json_mode=True,
            )
        )

        count = db.scalar(select(func.count()).select_from(AIUsage))
        assert count == 2
        assert all(usage.cost_usd == 0 for usage in db.scalars(select(AIUsage)))


def test_gateway_blocks_calls_after_budget_is_exhausted(
    db_session_factory: sessionmaker[Session],
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        ai_provider="local",
        ai_monthly_budget_usd=0,
    )
    with db_session_factory() as db:
        gateway = AIGateway(db, settings)

        with pytest.raises(AppException) as exc_info:
            asyncio.run(
                gateway.complete(
                    INTENT_MESSAGES,
                    operation="intent",
                    user_id=99,
                    json_mode=True,
                )
            )

        assert exc_info.value.code == "AI_QUOTA_EXCEEDED"
        assert exc_info.value.status_code == 429
