"""Current-user AI usage and budget endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import AIUsage
from app.schemas.account import AIUsageSummary

router = APIRouter(prefix="/account", tags=["account"])


@router.get(
    "/ai-usage",
    response_model=AIUsageSummary,
    summary="Get current month AI usage and budget",
)
def get_ai_usage(
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> AIUsageSummary:
    """Aggregate only the authenticated user's metered calls for this month."""

    today = datetime.now(UTC).date()
    period_start = date(today.year, today.month, 1)
    period_end = (
        date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    )
    base_filter = (
        AIUsage.user_id == user.id,
        AIUsage.created_at >= period_start,
        AIUsage.created_at < period_end,
    )
    calls = db.scalar(select(func.count()).select_from(AIUsage).where(*base_filter)) or 0
    failed_calls = (
        db.scalar(
            select(func.count())
            .select_from(AIUsage)
            .where(*base_filter, AIUsage.success.is_(False))
        )
        or 0
    )
    prompt_tokens = db.scalar(
        select(func.coalesce(func.sum(AIUsage.prompt_tokens), 0)).where(*base_filter)
    )
    completion_tokens = db.scalar(
        select(func.coalesce(func.sum(AIUsage.completion_tokens), 0)).where(*base_filter)
    )
    cost = Decimal(
        str(
            db.scalar(select(func.coalesce(func.sum(AIUsage.cost_usd), 0)).where(*base_filter)) or 0
        )
    )
    budget = Decimal(str(settings.ai_monthly_budget_usd))
    return AIUsageSummary(
        period_start=period_start,
        period_end=period_end,
        calls=int(calls),
        successful_calls=int(calls) - int(failed_calls),
        failed_calls=int(failed_calls),
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(prompt_tokens or 0) + int(completion_tokens or 0),
        cost_usd=float(cost.quantize(Decimal("0.000001"))),
        monthly_budget_usd=float(budget),
        remaining_budget_usd=float(max(budget - cost, Decimal("0"))),
    )
