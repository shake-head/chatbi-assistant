"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import authentication_error
from app.core.security import decode_access_token
from app.db.session import get_db, get_session_factory
from app.models import User
from app.services.ai_gateway import AIGateway

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]


def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: BearerCredentials,
) -> User:
    """Resolve the bearer token to an active user."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise authentication_error()
    user_id = decode_access_token(credentials.credentials, settings)
    user = db.get(User, user_id)
    if user is None:
        raise authentication_error("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_ai_gateway(db: DbSession, settings: AppSettings) -> AIGateway:
    """Provide the only permitted route to model providers."""

    return AIGateway(db, settings)


AIGatewayDep = Annotated[AIGateway, Depends(get_ai_gateway)]
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]


async def enforce_ai_rate_limit(user: CurrentUser, settings: AppSettings) -> None:
    """Apply the per-user AI request limit."""

    from app.core.rate_limit import check_rate_limit

    await check_rate_limit(
        user_id=user.id,
        settings=settings,
        scope="ai",
        limit=settings.ai_rate_limit_requests,
    )


async def enforce_upload_rate_limit(user: CurrentUser, settings: AppSettings) -> None:
    """Apply the per-user upload limit."""

    from app.core.rate_limit import check_rate_limit

    await check_rate_limit(
        user_id=user.id,
        settings=settings,
        scope="upload",
        limit=settings.upload_rate_limit_requests,
    )


AIRateLimit = Annotated[None, Depends(enforce_ai_rate_limit)]
UploadRateLimit = Annotated[None, Depends(enforce_upload_rate_limit)]
