"""Uploaded datasets and their parsed schemas."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User


class Dataset(Base):
    """Metadata for a dataset stored outside the relational database."""

    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading', 'parsing', 'ready', 'failed')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    schema_json: Mapped[dict[str, Any]] = mapped_column(
        "schema",
        JSON,
        nullable=False,
        default=dict,
    )
    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="uploading",
        server_default="uploading",
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="datasets")
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="dataset",
        passive_deletes=True,
    )
