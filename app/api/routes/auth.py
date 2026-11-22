"""User registration and login endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.core.errors import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])


def _token_response(user: User, settings: AppSettings) -> TokenResponse:
    token, expires_in = create_access_token(user.id, settings)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
)
def register(
    payload: RegisterRequest,
    db: DbSession,
    settings: AppSettings,
) -> TokenResponse:
    """Create an account with a normalized email and bcrypt password hash."""

    email = str(payload.email).strip().lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise AppException(
            code="EMAIL_ALREADY_REGISTERED",
            message="An account with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppException(
            code="EMAIL_ALREADY_REGISTERED",
            message="An account with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    db.refresh(user)
    return _token_response(user, settings)


@router.post("/login", response_model=TokenResponse, summary="Log in")
def login(
    payload: LoginRequest,
    db: DbSession,
    settings: AppSettings,
) -> TokenResponse:
    """Authenticate an email and password."""

    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppException(
            code="INVALID_CREDENTIALS",
            message="Email or password is incorrect",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user, settings)


@router.get("/me", response_model=UserRead, summary="Get current user")
def get_me(user: CurrentUser) -> UserRead:
    """Return the authenticated user's public profile."""

    return UserRead.model_validate(user)
