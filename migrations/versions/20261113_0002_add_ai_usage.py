"""Add AI cost accounting and analysis audit fields.

Revision ID: 20261113_0002
Revises: 20261113_0001
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261113_0002"
down_revision: str | None = "20261113_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("error_message", sa.String(length=1000), nullable=True))
    op.add_column("messages", sa.Column("analysis_plan", sa.JSON(), nullable=True))

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_ai_usage_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_usage_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    op.create_index(op.f("ix_ai_usage_conversation_id"), "ai_usage", ["conversation_id"])
    op.create_index(op.f("ix_ai_usage_created_at"), "ai_usage", ["created_at"])
    op.create_index(op.f("ix_ai_usage_user_id"), "ai_usage", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_usage_user_id"), table_name="ai_usage")
    op.drop_index(op.f("ix_ai_usage_created_at"), table_name="ai_usage")
    op.drop_index(op.f("ix_ai_usage_conversation_id"), table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_column("messages", "analysis_plan")
    op.drop_column("datasets", "error_message")
