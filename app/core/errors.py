"""Application error types and consistent API error responses."""

from __future__ import annotations

from typing import Any


class AppException(Exception):
    """An expected application error mapped to one stable API error code."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


def authentication_error(message: str = "Authentication required") -> AppException:
    """Build a 401 error with the standard bearer challenge."""

    return AppException(
        code="UNAUTHORIZED",
        message=message,
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


def not_found_error(resource: str) -> AppException:
    """Build a 404 error without exposing whether another user owns the resource."""

    return AppException(
        code="NOT_FOUND",
        message=f"{resource} not found",
        status_code=404,
    )
