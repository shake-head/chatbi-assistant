"""Conversation and message response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ConversationRead(BaseModel):
    id: int
    dataset_id: int
    created_at: datetime


class MessageRead(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    chart_spec: dict[str, Any] | None = None
    result_table: list[dict[str, Any]] | None = None
    created_at: datetime
