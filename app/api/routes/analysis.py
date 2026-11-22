"""Chat analysis and conversation history endpoints."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import AIGatewayDep, AIRateLimit, AppSettings, CurrentUser, DbSession
from app.core.errors import AppException, not_found_error
from app.models import Conversation, Dataset, Message
from app.schemas.analysis import ChatRequest, ChatResponse
from app.schemas.conversation import ConversationRead, MessageRead
from app.services.analysis_service import answer_question, stream_answer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])


@router.post(
    "/datasets/{dataset_id}/chat",
    response_model=ChatResponse,
    summary="Ask a question about a dataset",
)
async def chat_with_dataset(
    dataset_id: int,
    payload: ChatRequest,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    gateway: AIGatewayDep,
    _rate_limit: AIRateLimit,
) -> ChatResponse:
    """Analyze a question and return chart, table, and conclusion."""

    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user.id))
    if dataset is None:
        raise not_found_error("Dataset")
    return await answer_question(
        db,
        settings,
        gateway,
        dataset=dataset,
        user_id=user.id,
        question=payload.question.strip(),
        conversation_id=payload.conversation_id,
    )


@router.post(
    "/datasets/{dataset_id}/chat/stream",
    summary="Ask a question with SSE progress and a final answer",
)
async def stream_chat_with_dataset(
    dataset_id: int,
    payload: ChatRequest,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    gateway: AIGatewayDep,
    _rate_limit: AIRateLimit,
) -> StreamingResponse:
    """Stream planning/execution status and a final ChatResponse event."""

    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user.id))
    if dataset is None:
        raise not_found_error("Dataset")

    async def event_source():
        try:
            async for event in stream_answer(
                db,
                settings,
                gateway,
                dataset=dataset,
                user_id=user.id,
                question=payload.question.strip(),
                conversation_id=payload.conversation_id,
            ):
                data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {event['event']}\ndata: {data}\n\n"
        except AppException as exc:
            data = json.dumps(
                {"code": exc.code, "message": exc.message, "detail": exc.detail},
                ensure_ascii=False,
                default=str,
            )
            yield f"event: error\ndata: {data}\n\n"
        except Exception:
            logger.exception("chat_stream_failed")
            data = json.dumps(
                {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/conversations",
    response_model=list[ConversationRead],
    summary="List current user's conversations",
)
def list_conversations(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationRead]:
    """List conversations without exposing other users' records."""

    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        ConversationRead(
            id=conversation.id,
            dataset_id=conversation.dataset_id,
            created_at=conversation.created_at,
        )
        for conversation in conversations
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
    summary="Get conversation messages",
)
def get_conversation_messages(
    conversation_id: int,
    db: DbSession,
    user: CurrentUser,
) -> list[MessageRead]:
    """Return ordered history for an owned conversation."""

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise not_found_error("Conversation")
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id.asc())
    ).all()
    return [
        MessageRead(
            id=message.id,
            role=message.role,
            content=message.content,
            chart_spec=message.chart_spec,
            result_table=message.result_table,
            created_at=message.created_at,
        )
        for message in messages
    ]


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an owned conversation",
)
def delete_conversation(
    conversation_id: int,
    db: DbSession,
    user: CurrentUser,
) -> Response:
    """Delete a conversation and all of its messages."""

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise not_found_error("Conversation")
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
