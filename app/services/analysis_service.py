"""End-to-end orchestration for one natural-language analysis question."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppException, not_found_error
from app.models import Conversation, Dataset, Message
from app.schemas.analysis import AnalysisPlan, ChartSpec, ChatResponse
from app.services.ai_gateway import AIGateway
from app.services.chart_builder import build_chart_spec
from app.services.conclusion_service import generate_conclusion
from app.services.intent_service import generate_analysis_plan
from app.services.sandbox_runner import execute_analysis_plan


async def answer_question(
    db: Session,
    settings: Settings,
    gateway: AIGateway,
    *,
    dataset: Dataset,
    user_id: int,
    question: str,
    conversation_id: int | None,
) -> ChatResponse:
    """Run the full pipeline and return its final response."""

    final_response: ChatResponse | None = None
    async for event in stream_answer(
        db,
        settings,
        gateway,
        dataset=dataset,
        user_id=user_id,
        question=question,
        conversation_id=conversation_id,
    ):
        if event["event"] == "final":
            final_response = ChatResponse.model_validate(event["data"])
    if final_response is None:
        raise AppException(
            code="ANALYSIS_EXECUTION_FAILED",
            message="The analysis did not produce a final response",
            status_code=500,
        )
    return final_response


async def stream_answer(
    db: Session,
    settings: Settings,
    gateway: AIGateway,
    *,
    dataset: Dataset,
    user_id: int,
    question: str,
    conversation_id: int | None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress events and one final ChatResponse payload."""

    if dataset.status != "ready" or not dataset.schema_json:
        raise AppException(
            code="DATASET_NOT_READY",
            message="The dataset is not ready for analysis",
            status_code=409,
        )

    conversation = _resolve_conversation(
        db,
        user_id=user_id,
        dataset_id=dataset.id,
        conversation_id=conversation_id,
    )
    yield {
        "event": "status",
        "data": {"stage": "conversation", "conversation_id": conversation.id},
    }
    history = _load_history(db, conversation.id, settings.max_history_messages)

    yield {"event": "status", "data": {"stage": "planning"}}
    plan = await generate_analysis_plan(
        gateway,
        user_id=user_id,
        question=question,
        schema=dataset.schema_json,
        history=history,
        max_result_rows=settings.analysis_max_result_rows,
    )
    yield {
        "event": "plan",
        "data": {
            "title": plan.title,
            "chart_type": plan.chart_type,
            "metrics": [metric.aggregation.value for metric in plan.metrics],
        },
    }

    yield {"event": "status", "data": {"stage": "executing"}}
    result = await asyncio.to_thread(
        execute_analysis_plan,
        settings,
        dataset.file_path,
        plan,
        dataset.schema_json,
    )
    chart = build_chart_spec(plan, result)
    yield {
        "event": "result",
        "data": {
            "row_count": result.row_count,
            "returned_rows": len(result.rows),
            "truncated": result.truncated,
            "columns": result.columns,
        },
    }

    yield {"event": "status", "data": {"stage": "concluding"}}
    conclusion = await generate_conclusion(
        gateway,
        user_id=user_id,
        question=question,
        plan=plan,
        result=result,
        conversation_id=conversation.id,
    )

    assistant_message = _persist_answer(
        db,
        conversation=conversation,
        question=question,
        conclusion=conclusion,
        chart=chart,
        plan=plan,
        result_rows=result.rows,
    )
    response = ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        question=question,
        conclusion=conclusion,
        chart_spec=chart,
        result_table=result.rows,
        row_count=result.row_count,
    )
    yield {"event": "final", "data": response.model_dump(mode="json")}


def _persist_answer(
    db: Session,
    *,
    conversation: Conversation,
    question: str,
    conclusion: str,
    chart: ChartSpec,
    plan: AnalysisPlan,
    result_rows: list[dict[str, Any]],
) -> Message:
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=question,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=conclusion,
        chart_spec=chart.model_dump(mode="json"),
        result_table=result_rows,
        analysis_plan=plan.model_dump(mode="json"),
    )
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


def _resolve_conversation(
    db: Session,
    *,
    user_id: int,
    dataset_id: int,
    conversation_id: int | None,
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(user_id=user_id, dataset_id=dataset_id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.dataset_id == dataset_id,
        )
    )
    if conversation is None:
        raise not_found_error("Conversation")
    return conversation


def _load_history(db: Session, conversation_id: int, limit: int) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return [
        {"role": message.role, "content": message.content[:2000]} for message in reversed(messages)
    ]
