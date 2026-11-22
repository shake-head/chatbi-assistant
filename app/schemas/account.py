"""Account-level AI usage and budget schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class AIUsageSummary(BaseModel):
    period_start: date
    period_end: date
    calls: int
    successful_calls: int
    failed_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    monthly_budget_usd: float
    remaining_budget_usd: float
